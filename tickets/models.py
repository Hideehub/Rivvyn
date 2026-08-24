from django.conf import settings
from django.db import models


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    class Category(models.TextChoices):
        BILLING = 'billing', 'Billing'
        BUG = 'bug', 'Bug'
        FEATURE_REQUEST = 'feature_request', 'Feature Request'
        ACCOUNT = 'account', 'Account'
        OTHER = 'other', 'Other'

    class Urgency(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    subject = models.CharField(max_length=255)
    description = models.TextField()
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tickets',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    # Populated by the AI triage call after submission (see tickets.services),
    # so left blank rather than required at creation time.
    category = models.CharField(max_length=20, choices=Category.choices, blank=True)
    urgency = models.CharField(max_length=10, choices=Urgency.choices, blank=True)
    urgency_reason = models.TextField(blank=True)
    draft_reply = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.subject}'


class TicketNote(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ticket_notes',
    )
    content = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Note on #{self.ticket_id} by {self.author}'
