from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from .forms import CustomerSignUpForm


class SignUpView(CreateView):
    form_class = CustomerSignUpForm
    template_name = 'accounts/signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class HomeView(LoginRequiredMixin, TemplateView):
    """Landing page after login. Replaced by the real ticket list /
    agent dashboard redirect once those views exist (steps 4 and 6)."""

    template_name = 'accounts/home.html'
