import logging
from typing import Literal

import anthropic
from django.conf import settings
from pydantic import BaseModel, Field

from .models import Ticket

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM_PROMPT = """You are a support ticket triage assistant for Rivyn, a small \
software company. Given a customer's support ticket, classify it and draft a first reply.

Categorize into exactly one of: Billing, Bug, Feature Request, Account, Other.

Assign urgency based on business impact and customer sentiment: Low, Medium, High, or \
Critical. Critical is reserved for outages, data loss, security issues, or anything that \
completely blocks a customer from using the product.

Write a short, professional draft reply (2-4 sentences) that acknowledges the issue and \
sets expectations. Do not promise specific timelines or commitments an agent hasn't \
approved. Sign off as "The Rivyn Support Team"."""

# Kept in sync with tickets.models.Ticket.Category / Ticket.Urgency choices.
_CategoryLiteral = Literal['billing', 'bug', 'feature_request', 'account', 'other']
_UrgencyLiteral = Literal['low', 'medium', 'high', 'critical']


class TicketTriageResult(BaseModel):
    category: _CategoryLiteral
    urgency: _UrgencyLiteral
    urgency_reason: str = Field(description='One sentence explaining the urgency assignment.')
    draft_reply: str = Field(description="A short, professional first response to the customer.")


class TriageError(Exception):
    """Raised when the AI triage call fails or returns an unusable result."""


def triage_ticket(ticket):
    """Classify `ticket` and draft a first reply, setting category/urgency/
    urgency_reason/draft_reply on the given instance (not saved here — the
    caller decides when to persist) and returning it.

    Calls the Anthropic API unless settings.AI_TRIAGE_MOCK is set (the
    default when no ANTHROPIC_API_KEY is configured), in which case a local
    keyword-based stub is used instead — see _mock_triage_ticket. Raises
    TriageError on any failure; callers decide whether to save the ticket
    without triage data, surface an error, or let the agent retry via
    "Regenerate AI suggestion".
    """
    if settings.AI_TRIAGE_MOCK:
        return _mock_triage_ticket(ticket)
    return _live_triage_ticket(ticket)


def _live_triage_ticket(ticket):
    if not settings.ANTHROPIC_API_KEY:
        raise TriageError('ANTHROPIC_API_KEY is not configured.')

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = client.messages.parse(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1024,
            timeout=30.0,
            system=TRIAGE_SYSTEM_PROMPT,
            messages=[{
                'role': 'user',
                'content': f'Subject: {ticket.subject}\n\nDescription:\n{ticket.description}',
            }],
            output_format=TicketTriageResult,
        )
    except anthropic.AuthenticationError as exc:
        logger.error('Anthropic API authentication failed - check ANTHROPIC_API_KEY: %s', exc)
        raise TriageError('AI triage is not configured correctly (authentication failed).') from exc
    except anthropic.RateLimitError as exc:
        logger.warning('Anthropic API rate limited during triage: %s', exc)
        raise TriageError('AI triage is temporarily rate-limited. Try again shortly.') from exc
    except anthropic.APIStatusError as exc:
        logger.warning('Anthropic API error during triage (status %s): %s', exc.status_code, exc)
        raise TriageError(f'AI triage failed (HTTP {exc.status_code}).') from exc
    except anthropic.APIConnectionError as exc:
        logger.warning('Could not reach the Anthropic API for triage: %s', exc)
        raise TriageError('Could not reach the AI triage service.') from exc

    result = response.parsed_output
    if result is None:
        raise TriageError('Model did not return a parseable triage result.')

    ticket.category = result.category
    ticket.urgency = result.urgency
    ticket.urgency_reason = result.urgency_reason
    ticket.draft_reply = result.draft_reply
    return ticket


_MOCK_CATEGORY_KEYWORDS = {
    Ticket.Category.BILLING: ('bill', 'invoice', 'charge', 'refund', 'payment', 'subscription', 'price'),
    Ticket.Category.BUG: ('bug', 'error', 'crash', 'broken', "doesn't work", 'not working', 'fails', 'exception'),
    Ticket.Category.FEATURE_REQUEST: ('feature', 'request', 'would be nice', 'suggestion', 'please add', 'wish'),
    Ticket.Category.ACCOUNT: ('password', 'log in', 'login', 'account', 'locked out', '2fa', 'sign in'),
}

_MOCK_URGENCY_KEYWORDS = {
    Ticket.Urgency.CRITICAL: (
        'down', 'outage', 'urgent', 'critical', 'data loss', 'security', 'asap',
        "can't access", 'cannot access', 'losing money',
    ),
    Ticket.Urgency.HIGH: ('blocked', 'broken', 'error', 'crash', 'important', 'not working'),
    Ticket.Urgency.LOW: ('minor', 'small', 'cosmetic', 'no rush', 'when you get a chance'),
}

_MOCK_URGENCY_REASONS = {
    Ticket.Urgency.CRITICAL: 'Language suggests the customer is fully blocked or facing a security/data issue.',
    Ticket.Urgency.HIGH: 'The ticket describes a clear error or broken functionality.',
    Ticket.Urgency.MEDIUM: 'No strong urgency signals were found; defaulting to standard priority.',
    Ticket.Urgency.LOW: "The customer's language suggests this is minor or non-blocking.",
}


def _match_keyword_map(text, keyword_map, default):
    for value, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            return value
    return default


def _mock_triage_ticket(ticket):
    """Offline stand-in for the Anthropic call (see settings.AI_TRIAGE_MOCK):
    a simple keyword match against the subject/description, so the ticket
    flow can be demoed without an Anthropic account."""
    text = f'{ticket.subject} {ticket.description}'.lower()

    ticket.category = _match_keyword_map(text, _MOCK_CATEGORY_KEYWORDS, default=Ticket.Category.OTHER)
    ticket.urgency = _match_keyword_map(text, _MOCK_URGENCY_KEYWORDS, default=Ticket.Urgency.MEDIUM)
    ticket.urgency_reason = _MOCK_URGENCY_REASONS[ticket.urgency]
    ticket.draft_reply = (
        f'Hi, thanks for reaching out about "{ticket.subject}". '
        f"We've logged this as a {ticket.get_category_display().lower()} issue and "
        f'will follow up shortly.\n\n- The Rivyn Support Team'
    )

    logger.info('Used mock AI triage for a ticket (no ANTHROPIC_API_KEY configured).')
    return ticket
