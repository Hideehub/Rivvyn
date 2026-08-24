from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
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
    """Landing page after login. Customers land on their ticket list;
    agents see a placeholder until the real dashboard exists (step 6)."""

    template_name = 'accounts/home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_customer:
            return redirect('tickets:list')
        return super().get(request, *args, **kwargs)
