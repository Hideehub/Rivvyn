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


class TicketQueueFilterForm(forms.Form):
    """GET filters for the agent queue. Every field is optional; an invalid value
    just fails validation for that field, and the view ignores it."""

    status = forms.ChoiceField(required=False, choices=[('', 'All statuses'), *Ticket.Status.choices])
    urgency = forms.ChoiceField(required=False, choices=[('', 'All urgencies'), *Ticket.Urgency.choices])
    category = forms.ChoiceField(required=False, choices=[('', 'All categories'), *Ticket.Category.choices])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'field-input'


class TicketStatusForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'field-input'}),
        }
