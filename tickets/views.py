import logging

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View

from accounts.mixins import AgentRequiredMixin, CustomerRequiredMixin

from .forms import AgentReplyForm, TicketForm, TicketNoteForm, TicketQueueFilterForm, TicketStatusForm
from .models import Ticket, TicketNote
from .services import TriageError, triage_ticket

logger = logging.getLogger(__name__)


class TicketCreateView(CustomerRequiredMixin, CreateView):
    form_class = TicketForm
    template_name = 'tickets/ticket_form.html'

    def form_valid(self, form):
        form.instance.customer = self.request.user
        response = super().form_valid(form)

        try:
            triage_ticket(self.object)
            self.object.save()
        except TriageError:
            logger.warning('AI triage failed for ticket %s', self.object.pk, exc_info=True)
            messages.warning(
                self.request,
                "Your ticket was submitted, but automatic triage didn't complete. "
                "An agent will review it shortly.",
            )

        return response

    def get_success_url(self):
        return reverse('tickets:detail', args=[self.object.pk])


class TicketListView(CustomerRequiredMixin, ListView):
    template_name = 'tickets/ticket_list.html'
    context_object_name = 'tickets'

    def get_queryset(self):
        return Ticket.objects.filter(customer=self.request.user)


class TicketDetailView(CustomerRequiredMixin, DetailView):
    model = Ticket
    template_name = 'tickets/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        # Customers may only view their own tickets.
        return Ticket.objects.filter(customer=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['notes'] = self.object.notes.filter(is_internal=False)
        return context


class AgentTicketQueueView(AgentRequiredMixin, ListView):
    """All tickets for agents. Untriaged tickets (blank urgency) come first since
    nobody has assessed them yet, then Critical → Low; oldest first within each."""

    template_name = 'tickets/agent_queue.html'
    context_object_name = 'tickets'

    def get_queryset(self):
        self.filter_form = TicketQueueFilterForm(self.request.GET or None)
        queryset = Ticket.objects.select_related('customer').annotate(
            urgency_rank=Case(
                When(urgency='', then=Value(0)),
                When(urgency=Ticket.Urgency.CRITICAL, then=Value(1)),
                When(urgency=Ticket.Urgency.HIGH, then=Value(2)),
                When(urgency=Ticket.Urgency.MEDIUM, then=Value(3)),
                When(urgency=Ticket.Urgency.LOW, then=Value(4)),
                default=Value(5),
                output_field=IntegerField(),
            ),
        )
        # is_valid() populates cleaned_data with only the fields that passed,
        # so a bad value in one filter is dropped without breaking the others.
        self.filter_form.is_valid()
        filters = {
            field: value
            for field, value in getattr(self.filter_form, 'cleaned_data', {}).items()
            if value
        }
        return queryset.filter(**filters).order_by('urgency_rank', 'created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        return context


class AgentTicketDetailView(AgentRequiredMixin, DetailView):
    """Full ticket for agents: AI triage fields and every note, internal ones included."""

    model = Ticket
    template_name = 'tickets/agent_ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        return Ticket.objects.select_related('customer')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['notes'] = self.object.notes.select_related('author')
        context['status_form'] = TicketStatusForm(instance=self.object)
        context['note_form'] = TicketNoteForm()
        context['reply_form'] = AgentReplyForm(initial={'content': self.object.draft_reply})
        context['ai_triage_mock'] = settings.AI_TRIAGE_MOCK
        return context


class AgentTicketStatusUpdateView(AgentRequiredMixin, UpdateView):
    """POST-only: the status form lives on the agent detail page."""

    model = Ticket
    form_class = TicketStatusForm
    http_method_names = ['post']

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Status changed to {self.object.get_status_display()}.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'That status is not valid. Nothing was changed.')
        return redirect('tickets:agent_detail', pk=self.object.pk)

    def get_success_url(self):
        return reverse('tickets:agent_detail', args=[self.object.pk])


class AgentTicketRegenerateTriageView(AgentRequiredMixin, View):
    """POST-only: re-runs AI triage and overwrites the ticket's AI fields. On failure
    nothing is saved, so the previous suggestion (if any) stays."""

    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        ticket = get_object_or_404(Ticket, pk=kwargs['pk'])
        try:
            triage_ticket(ticket)
        except TriageError as exc:
            logger.warning('AI triage regeneration failed for ticket %s', ticket.pk, exc_info=True)
            messages.error(request, f"Couldn't regenerate the AI suggestion: {exc}")
        else:
            ticket.save(update_fields=['category', 'urgency', 'urgency_reason', 'draft_reply', 'updated_at'])
            messages.success(request, 'AI suggestion regenerated.')
        return redirect('tickets:agent_detail', pk=ticket.pk)


class AgentTicketSendReplyView(AgentRequiredMixin, FormView):
    """POST-only: sends the agent's (possibly edited) AI draft as a public note.
    draft_reply is left as the AI wrote it, so regenerating never touches a sent reply.
    An Open ticket moves to In Progress; any other status is left alone."""

    form_class = AgentReplyForm
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        self.ticket = get_object_or_404(Ticket, pk=kwargs['pk'])
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            TicketNote.objects.create(
                ticket=self.ticket,
                author=self.request.user,
                content=form.cleaned_data['content'],
                is_internal=False,
            )
            # Conditional UPDATE: only an Open row changes, so a status another
            # agent set in the meantime is never overwritten.
            moved = Ticket.objects.filter(pk=self.ticket.pk, status=Ticket.Status.OPEN).update(
                status=Ticket.Status.IN_PROGRESS, updated_at=timezone.now(),
            )
        messages.success(self.request, 'Reply sent. Status changed to In Progress.' if moved else 'Reply sent.')
        return redirect('tickets:agent_detail', pk=self.ticket.pk)

    def form_invalid(self, form):
        messages.error(self.request, 'The reply was empty. Nothing was sent.')
        return redirect('tickets:agent_detail', pk=self.ticket.pk)


class AgentTicketNoteCreateView(AgentRequiredMixin, CreateView):
    """POST-only: the note form lives on the agent detail page."""

    form_class = TicketNoteForm
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        self.ticket = get_object_or_404(Ticket, pk=kwargs['pk'])
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.ticket = self.ticket
        form.instance.author = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Internal note added.' if self.object.is_internal else 'Note added.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'The note was empty. Nothing was added.')
        return redirect('tickets:agent_detail', pk=self.ticket.pk)

    def get_success_url(self):
        return reverse('tickets:agent_detail', args=[self.ticket.pk])
