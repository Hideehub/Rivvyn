import logging

from django.conf import settings
from django.contrib import messages
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import AgentRequiredMixin, CustomerRequiredMixin

from .forms import TicketForm, TicketQueueFilterForm, TicketStatusForm
from .models import Ticket
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
        context['ai_triage_mock'] = settings.AI_TRIAGE_MOCK
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
