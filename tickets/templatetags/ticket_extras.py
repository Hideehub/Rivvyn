from django import template

from tickets.models import Ticket

register = template.Library()

_URGENCY_BADGE_CLASSES = {
    Ticket.Urgency.LOW: 'badge-urgency-low',
    Ticket.Urgency.MEDIUM: 'badge-urgency-medium',
    Ticket.Urgency.HIGH: 'badge-urgency-high',
    Ticket.Urgency.CRITICAL: 'badge-urgency-critical',
}

_STATUS_BADGE_CLASSES = {
    Ticket.Status.OPEN: 'badge-status-open',
    Ticket.Status.IN_PROGRESS: 'badge-status-in-progress',
    Ticket.Status.RESOLVED: 'badge-status-resolved',
    Ticket.Status.CLOSED: 'badge-status-closed',
}


@register.filter
def urgency_badge_class(urgency):
    return _URGENCY_BADGE_CLASSES.get(urgency, 'badge-category')


@register.filter
def status_badge_class(status):
    return _STATUS_BADGE_CLASSES.get(status, 'badge-category')
