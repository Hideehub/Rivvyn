from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class AgentRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restricts a view to authenticated users with role=agent."""

    def test_func(self):
        return self.request.user.is_agent

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied('Agent access required.')


class CustomerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restricts a view to authenticated users with role=customer."""

    def test_func(self):
        return self.request.user.is_customer

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied('Customer access required.')
