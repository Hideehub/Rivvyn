from django import forms

from .models import Ticket


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['subject', 'description']
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "What's going on?"}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Give us as much detail as you can - steps to reproduce, error messages, etc.',
            }),
        }
