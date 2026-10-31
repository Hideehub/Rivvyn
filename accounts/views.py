from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, View

from .forms import CustomerSignUpForm


class SignUpView(CreateView):
    form_class = CustomerSignUpForm
    template_name = 'accounts/signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class HomeView(LoginRequiredMixin, View):
    """Landing URL after login: agents go to the ticket queue, customers to their ticket list."""

    def get(self, request, *args, **kwargs):
        if request.user.is_agent:
            return redirect('tickets:agent_queue')
        return redirect('tickets:list')
