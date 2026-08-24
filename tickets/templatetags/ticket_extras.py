from django import template

from tickets.models import Ticket

register = template.Library()

_URGENCY_BADGE_CLASSES = {
    Ticket.Urgency.LOW: 'rivyn-badge-urgency-low',
    Ticket.Urgency.MEDIUM: 'rivyn-badge-urgency-medium',
    Ticket.Urgency.HIGH: 'rivyn-badge-urgency-high',
    Ticket.Urgency.CRITICAL: 'rivyn-badge-urgency-critical',
}


@register.filter
def urgency_badge_class(urgency):
    return _URGENCY_BADGE_CLASSES.get(urgency, 'rivyn-badge-category')
