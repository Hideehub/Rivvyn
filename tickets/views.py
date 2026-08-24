from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView

from accounts.mixins import CustomerRequiredMixin

from .forms import TicketForm
from .models import Ticket


class TicketCreateView(CustomerRequiredMixin, CreateView):
    form_class = TicketForm
    template_name = 'tickets/ticket_form.html'

    def form_valid(self, form):
        form.instance.customer = self.request.user
        # AI triage call (category/urgency/draft_reply) is wired in step 5.
        return super().form_valid(form)

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
