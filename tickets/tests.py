from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import Ticket, TicketNote
from .services import TicketTriageResult, TriageError, triage_ticket


class TicketCreateViewTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        self.client.force_login(self.customer)

    @patch('tickets.views.triage_ticket', side_effect=TriageError('not configured'))
    def test_submit_ticket_sets_customer_and_defaults(self, mock_triage):
        response = self.client.post(reverse('tickets:create'), {
            'subject': 'Cannot log in',
            'description': 'I get an error when I try to log in.',
        })
        ticket = Ticket.objects.get(subject='Cannot log in')
        self.assertEqual(ticket.customer, self.customer)
        self.assertEqual(ticket.status, Ticket.Status.OPEN)
        self.assertEqual(ticket.category, '')
        self.assertRedirects(response, reverse('tickets:detail', args=[ticket.pk]))

    @patch('tickets.views.triage_ticket')
    def test_submit_ticket_saves_triage_result(self, mock_triage):
        def fake_triage(ticket):
            ticket.category = Ticket.Category.BUG
            ticket.urgency = Ticket.Urgency.HIGH
            ticket.urgency_reason = 'Customer cannot log in at all.'
            ticket.draft_reply = 'Thanks for reporting this - looking into it now.'
            return ticket

        mock_triage.side_effect = fake_triage

        self.client.post(reverse('tickets:create'), {
            'subject': 'Cannot log in',
            'description': 'I get an error when I try to log in.',
        })
        ticket = Ticket.objects.get(subject='Cannot log in')
        self.assertEqual(ticket.category, Ticket.Category.BUG)
        self.assertEqual(ticket.urgency, Ticket.Urgency.HIGH)
        self.assertTrue(ticket.urgency_reason)
        self.assertTrue(ticket.draft_reply)

    @patch('tickets.views.triage_ticket', side_effect=TriageError('boom'))
    def test_submit_ticket_survives_triage_failure(self, mock_triage):
        response = self.client.post(reverse('tickets:create'), {
            'subject': 'Cannot log in',
            'description': 'I get an error when I try to log in.',
        }, follow=True)
        self.assertTrue(Ticket.objects.filter(subject='Cannot log in').exists())
        self.assertContains(response, 'automatic triage')

    def test_agent_cannot_submit_ticket(self):
        agent = User.objects.create_user(username='dave', password='pw', role=User.Role.AGENT)
        self.client.force_login(agent)
        response = self.client.post(reverse('tickets:create'), {
            'subject': 'Should be blocked',
            'description': 'Agents do not submit tickets.',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Ticket.objects.filter(subject='Should be blocked').exists())

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(reverse('tickets:create'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('tickets:create')}")


class TicketListViewTests(TestCase):
    def test_customer_sees_only_own_tickets(self):
        carol = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        erin = User.objects.create_user(username='erin', password='pw', role=User.Role.CUSTOMER)
        Ticket.objects.create(subject='Carol ticket', description='...', customer=carol)
        Ticket.objects.create(subject='Erin ticket', description='...', customer=erin)

        self.client.force_login(carol)
        response = self.client.get(reverse('tickets:list'))
        self.assertContains(response, 'Carol ticket')
        self.assertNotContains(response, 'Erin ticket')


class TicketDetailViewTests(TestCase):
    def test_customer_cannot_view_another_customers_ticket(self):
        carol = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        erin = User.objects.create_user(username='erin', password='pw', role=User.Role.CUSTOMER)
        ticket = Ticket.objects.create(subject='Erin ticket', description='...', customer=erin)

        self.client.force_login(carol)
        response = self.client.get(reverse('tickets:detail', args=[ticket.pk]))
        self.assertEqual(response.status_code, 404)

    def test_internal_notes_hidden_from_customer(self):
        carol = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        dave = User.objects.create_user(username='dave', password='pw', role=User.Role.AGENT)
        ticket = Ticket.objects.create(subject='Ticket', description='...', customer=carol)
        TicketNote.objects.create(ticket=ticket, author=dave, content='Internal note', is_internal=True)
        TicketNote.objects.create(ticket=ticket, author=dave, content='Public update', is_internal=False)

        self.client.force_login(carol)
        response = self.client.get(reverse('tickets:detail', args=[ticket.pk]))
        self.assertContains(response, 'Public update')
        self.assertNotContains(response, 'Internal note')


class TriageServiceTests(TestCase):
    def _fake_response(self, **overrides):
        defaults = dict(
            category='bug',
            urgency='high',
            urgency_reason='Customer cannot access the product at all.',
            draft_reply='Thanks for reaching out - we are looking into this right away.',
        )
        defaults.update(overrides)
        response = MagicMock()
        response.parsed_output = TicketTriageResult(**defaults)
        return response

    @override_settings(AI_TRIAGE_MOCK=False, ANTHROPIC_API_KEY='sk-ant-test-key')
    @patch('tickets.services.anthropic.Anthropic')
    def test_triage_ticket_sets_fields_on_success(self, mock_anthropic_cls):
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.parse.return_value = self._fake_response()

        ticket = Ticket(subject='App crashes on launch', description='It just crashes every time.')
        result = triage_ticket(ticket)

        self.assertIs(result, ticket)
        self.assertEqual(ticket.category, 'bug')
        self.assertEqual(ticket.urgency, 'high')
        self.assertTrue(ticket.urgency_reason)
        self.assertTrue(ticket.draft_reply)

    @override_settings(AI_TRIAGE_MOCK=False, ANTHROPIC_API_KEY='')
    def test_triage_ticket_requires_api_key(self):
        ticket = Ticket(subject='x', description='y')
        with self.assertRaises(TriageError):
            triage_ticket(ticket)

    @override_settings(AI_TRIAGE_MOCK=False, ANTHROPIC_API_KEY='sk-ant-test-key')
    @patch('tickets.services.anthropic.Anthropic')
    def test_triage_ticket_wraps_connection_errors(self, mock_anthropic_cls):
        import anthropic

        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.parse.side_effect = anthropic.APIConnectionError(request=MagicMock())

        ticket = Ticket(subject='x', description='y')
        with self.assertRaises(TriageError):
            triage_ticket(ticket)

    @override_settings(AI_TRIAGE_MOCK=False, ANTHROPIC_API_KEY='sk-ant-test-key')
    @patch('tickets.services.anthropic.Anthropic')
    def test_triage_ticket_raises_when_unparseable(self, mock_anthropic_cls):
        mock_client = mock_anthropic_cls.return_value
        response = MagicMock()
        response.parsed_output = None
        mock_client.messages.parse.return_value = response

        ticket = Ticket(subject='x', description='y')
        with self.assertRaises(TriageError):
            triage_ticket(ticket)


class TriageServiceHTTPTests(TestCase):
    """Runs the real SDK `messages.parse()` path with only the HTTP layer faked,
    so SDK/pydantic incompatibilities fail here instead of in production."""

    @override_settings(
        AI_TRIAGE_MOCK=False,
        ANTHROPIC_API_KEY='sk-ant-test-key',
        ANTHROPIC_MODEL='claude-sonnet-5-5',
    )
    def test_live_triage_parses_response_into_triage_result(self):
        import json

        import anthropic
        import httpx2

        sent = {}

        def handler(request):
            sent['body'] = json.loads(request.content)
            output = {
                'category': 'billing',
                'urgency': 'high',
                'urgency_reason': 'Customer was charged twice.',
                'draft_reply': 'Thanks for flagging this - we are looking into the duplicate charge.',
            }
            return httpx2.Response(200, json={
                'id': 'msg_test',
                'type': 'message',
                'role': 'assistant',
                'model': sent['body']['model'],
                'content': [{'type': 'text', 'text': json.dumps(output)}],
                'stop_reason': 'end_turn',
                'stop_sequence': None,
                'usage': {'input_tokens': 10, 'output_tokens': 10},
            })

        real_client_cls = anthropic.Anthropic

        def client_with_fake_transport(**kwargs):
            return real_client_cls(
                **kwargs,
                http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
            )

        ticket = Ticket(subject='Charged twice', description='My card was billed twice this month.')
        with patch('tickets.services.anthropic.Anthropic', side_effect=client_with_fake_transport):
            triage_ticket(ticket)

        self.assertEqual(sent['body']['model'], 'claude-sonnet-5-5')
        self.assertEqual(sent['body']['output_config']['format']['type'], 'json_schema')
        self.assertEqual(ticket.category, 'billing')
        self.assertEqual(ticket.urgency, 'high')
        self.assertEqual(ticket.urgency_reason, 'Customer was charged twice.')
        self.assertIn('duplicate charge', ticket.draft_reply)


class MockTriageTests(TestCase):
    @override_settings(AI_TRIAGE_MOCK=True)
    def test_mock_triage_classifies_billing_and_low_urgency(self):
        ticket = Ticket(
            subject='Question about my invoice',
            description='No rush, but can you clarify a charge on my last invoice?',
        )
        result = triage_ticket(ticket)

        self.assertIs(result, ticket)
        self.assertEqual(ticket.category, Ticket.Category.BILLING)
        self.assertEqual(ticket.urgency, Ticket.Urgency.LOW)
        self.assertTrue(ticket.urgency_reason)
        self.assertIn('Rivyn Support Team', ticket.draft_reply)

    @override_settings(AI_TRIAGE_MOCK=True)
    def test_mock_triage_classifies_critical_bug(self):
        ticket = Ticket(
            subject='Site is down',
            description="This is urgent, I can't access my account at all, it's a total outage.",
        )
        result = triage_ticket(ticket)

        self.assertEqual(result.urgency, Ticket.Urgency.CRITICAL)

    @override_settings(AI_TRIAGE_MOCK=True)
    def test_mock_triage_defaults_to_other_and_medium(self):
        ticket = Ticket(subject='General question', description='Just wondering how this works.')
        result = triage_ticket(ticket)

        self.assertEqual(result.category, Ticket.Category.OTHER)
        self.assertEqual(result.urgency, Ticket.Urgency.MEDIUM)


class AgentTicketQueueViewTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username='dave', password='pw', role=User.Role.AGENT)
        self.carol = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        self.erin = User.objects.create_user(username='erin', password='pw', role=User.Role.CUSTOMER)
        self.url = reverse('tickets:agent_queue')

    def _ticket(self, subject, minutes_ago, customer=None, **fields):
        ticket = Ticket.objects.create(
            subject=subject, description='...', customer=customer or self.carol, **fields,
        )
        # created_at is auto_now_add, so set it with update() to control ordering.
        Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
        return ticket

    def _subjects(self, response):
        return [ticket.subject for ticket in response.context['tickets']]

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_customer_forbidden(self):
        self.client.force_login(self.carol)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_agent_sees_tickets_from_all_customers(self):
        self._ticket('Carol ticket', 10)
        self._ticket('Erin ticket', 5, customer=self.erin)

        self.client.force_login(self.agent)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(self._subjects(response), ['Carol ticket', 'Erin ticket'])

    def test_untriaged_first_then_by_urgency_then_oldest_first(self):
        self._ticket('Low', 50, urgency=Ticket.Urgency.LOW)
        self._ticket('High newer', 10, urgency=Ticket.Urgency.HIGH)
        self._ticket('High older', 40, urgency=Ticket.Urgency.HIGH)
        self._ticket('Critical', 5, urgency=Ticket.Urgency.CRITICAL)
        self._ticket('Medium', 30, urgency=Ticket.Urgency.MEDIUM)
        self._ticket('Untriaged', 1)

        self.client.force_login(self.agent)
        response = self.client.get(self.url)

        self.assertEqual(
            self._subjects(response),
            ['Untriaged', 'Critical', 'High older', 'High newer', 'Medium', 'Low'],
        )

    def test_untriaged_ticket_shows_needs_triage_badge(self):
        self._ticket('Untriaged', 1)

        self.client.force_login(self.agent)
        response = self.client.get(self.url)

        self.assertContains(response, 'Needs triage')

    def test_filter_by_status(self):
        self._ticket('Open one', 10)
        self._ticket('Resolved one', 5, status=Ticket.Status.RESOLVED)

        self.client.force_login(self.agent)
        response = self.client.get(self.url, {'status': 'resolved'})

        self.assertEqual(self._subjects(response), ['Resolved one'])

    def test_filter_by_urgency(self):
        self._ticket('Critical one', 10, urgency=Ticket.Urgency.CRITICAL)
        self._ticket('Low one', 5, urgency=Ticket.Urgency.LOW)

        self.client.force_login(self.agent)
        response = self.client.get(self.url, {'urgency': 'low'})

        self.assertEqual(self._subjects(response), ['Low one'])

    def test_filter_by_category(self):
        self._ticket('Billing one', 10, category=Ticket.Category.BILLING)
        self._ticket('Bug one', 5, category=Ticket.Category.BUG)

        self.client.force_login(self.agent)
        response = self.client.get(self.url, {'category': 'bug'})

        self.assertEqual(self._subjects(response), ['Bug one'])

    def test_invalid_filter_value_is_ignored(self):
        self._ticket('Billing one', 10, category=Ticket.Category.BILLING)
        self._ticket('Bug one', 5, category=Ticket.Category.BUG)

        self.client.force_login(self.agent)
        response = self.client.get(self.url, {'status': 'not-a-status', 'category': 'bug'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._subjects(response), ['Bug one'])

    def test_navbar_queue_link_only_for_agents(self):
        self.client.force_login(self.agent)
        self.assertContains(self.client.get(self.url), f'href="{self.url}"')

        self.client.force_login(self.carol)
        self.assertNotContains(self.client.get(reverse('tickets:list')), f'href="{self.url}"')


class AgentTicketDetailViewTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username='dave', password='pw', role=User.Role.AGENT)
        self.carol = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        self.ticket = Ticket.objects.create(
            subject='Charged twice',
            description='My card was billed twice.',
            customer=self.carol,
            category=Ticket.Category.BILLING,
            urgency=Ticket.Urgency.HIGH,
            urgency_reason='Customer lost money.',
            draft_reply='Sorry about the double charge - we are on it.',
        )
        self.url = reverse('tickets:agent_detail', args=[self.ticket.pk])

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_customer_forbidden_even_for_own_ticket(self):
        self.client.force_login(self.carol)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_missing_ticket_returns_404(self):
        self.client.force_login(self.agent)
        response = self.client.get(reverse('tickets:agent_detail', args=[self.ticket.pk + 1]))
        self.assertEqual(response.status_code, 404)

    def test_agent_sees_ticket_and_ai_fields(self):
        self.client.force_login(self.agent)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My card was billed twice.')
        self.assertContains(response, 'carol')
        self.assertContains(response, 'badge-category')
        self.assertContains(response, 'badge-urgency-high')
        self.assertContains(response, 'Customer lost money.')
        self.assertContains(response, 'Sorry about the double charge - we are on it.')

    def test_untriaged_ticket_shows_needs_triage(self):
        ticket = Ticket.objects.create(subject='No triage', description='...', customer=self.carol)

        self.client.force_login(self.agent)
        response = self.client.get(reverse('tickets:agent_detail', args=[ticket.pk]))

        self.assertContains(response, 'Needs triage')
        self.assertContains(response, "Automatic triage hasn't run for this ticket yet.")

    def test_agent_sees_internal_and_public_notes_with_internal_marked(self):
        TicketNote.objects.create(ticket=self.ticket, author=self.agent, content='Public update', is_internal=False)
        TicketNote.objects.create(ticket=self.ticket, author=self.agent, content='Internal only', is_internal=True)

        self.client.force_login(self.agent)
        response = self.client.get(self.url)

        self.assertContains(response, 'Public update')
        self.assertContains(response, 'Internal only')
        self.assertContains(response, '>Internal</span>', count=1)

    def test_queue_links_to_agent_detail(self):
        self.client.force_login(self.agent)
        response = self.client.get(reverse('tickets:agent_queue'))
        self.assertContains(response, f'href="{self.url}"')


class AgentTicketStatusUpdateViewTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username='dave', password='pw', role=User.Role.AGENT)
        self.carol = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        self.ticket = Ticket.objects.create(subject='Broken export', description='...', customer=self.carol)
        self.url = reverse('tickets:agent_status', args=[self.ticket.pk])
        self.detail_url = reverse('tickets:agent_detail', args=[self.ticket.pk])

    def _status(self):
        self.ticket.refresh_from_db()
        return self.ticket.status

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(self.url, {'status': 'resolved'})
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False)
        self.assertEqual(self._status(), Ticket.Status.OPEN)

    def test_customer_forbidden(self):
        self.client.force_login(self.carol)
        response = self.client.post(self.url, {'status': 'resolved'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._status(), Ticket.Status.OPEN)

    def test_agent_can_move_ticket_through_every_status(self):
        self.client.force_login(self.agent)
        for status in ['in_progress', 'resolved', 'closed', 'open']:
            response = self.client.post(self.url, {'status': status})
            self.assertRedirects(response, self.detail_url)
            self.assertEqual(self._status(), status)

    def test_success_message_shown(self):
        self.client.force_login(self.agent)
        response = self.client.post(self.url, {'status': 'in_progress'}, follow=True)
        self.assertContains(response, 'Status changed to In Progress.')

    def test_invalid_status_rejected_and_unchanged(self):
        self.client.force_login(self.agent)
        response = self.client.post(self.url, {'status': 'deleted'}, follow=True)
        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, 'That status is not valid. Nothing was changed.')
        self.assertEqual(self._status(), Ticket.Status.OPEN)

    def test_get_not_allowed(self):
        self.client.force_login(self.agent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_detail_page_shows_status_form_with_current_status(self):
        self.ticket.status = Ticket.Status.RESOLVED
        self.ticket.save()

        self.client.force_login(self.agent)
        response = self.client.get(self.detail_url)

        self.assertContains(response, f'action="{self.url}"')
        self.assertContains(response, '<option value="resolved" selected>Resolved</option>', html=True)
