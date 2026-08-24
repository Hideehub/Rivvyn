from django import forms

from .models import Ticket


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['subject', 'description']
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'field-input', 'placeholder': "What's going on?"}),
            'description': forms.Textarea(attrs={
                'class': 'field-input',
                'rows': 6,
                'placeholder': 'Give us as much detail as you can - steps to reproduce, error messages, etc.',
            }),
        }
