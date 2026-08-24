from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class CustomerSignUpForm(UserCreationForm):
    """Public self-signup. Always creates a Customer — agent accounts are
    provisioned separately (via Django admin) so no one can grant themselves
    agent access through this form."""

    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CUSTOMER
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user
