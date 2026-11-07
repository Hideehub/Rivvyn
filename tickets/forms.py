from django import forms

from .models import Ticket, TicketNote


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


class AgentReplyForm(forms.Form):
    """The agent's edited copy of the AI draft. Sending it creates a public note;
    Ticket.draft_reply itself is never written from this form."""

    content = forms.CharField(
        label='Reply to customer',
        widget=forms.Textarea(attrs={'class': 'field-input', 'rows': 6}),
    )


class TicketNoteForm(forms.ModelForm):
    class Meta:
        model = TicketNote
        fields = ['content', 'is_internal']
        labels = {
            'content': 'Add a note',
            'is_internal': 'Internal (agents only, hidden from the customer)',
        }
        widgets = {
            'content': forms.Textarea(attrs={'class': 'field-input', 'rows': 4}),
            'is_internal': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-slate-300 text-blue-600'}),
        }
