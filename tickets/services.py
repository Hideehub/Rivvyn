import logging
from typing import Literal

import anthropic
from django.conf import settings
from pydantic import BaseModel, Field

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
    """Call the Anthropic API to classify `ticket` and draft a first reply.

    On success, sets category/urgency/urgency_reason/draft_reply on the given
    ticket instance (not saved here — the caller decides when to persist) and
    returns it. Raises TriageError on any failure; callers decide whether to
    save the ticket without triage data, surface an error, or let the agent
    retry via "Regenerate AI suggestion".
    """
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
