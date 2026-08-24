from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

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

    @override_settings(ANTHROPIC_API_KEY='sk-ant-test-key')
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

    @override_settings(ANTHROPIC_API_KEY='')
    def test_triage_ticket_requires_api_key(self):
        ticket = Ticket(subject='x', description='y')
        with self.assertRaises(TriageError):
            triage_ticket(ticket)

    @override_settings(ANTHROPIC_API_KEY='sk-ant-test-key')
    @patch('tickets.services.anthropic.Anthropic')
    def test_triage_ticket_wraps_connection_errors(self, mock_anthropic_cls):
        import anthropic

        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.parse.side_effect = anthropic.APIConnectionError(request=MagicMock())

        ticket = Ticket(subject='x', description='y')
        with self.assertRaises(TriageError):
            triage_ticket(ticket)

    @override_settings(ANTHROPIC_API_KEY='sk-ant-test-key')
    @patch('tickets.services.anthropic.Anthropic')
    def test_triage_ticket_raises_when_unparseable(self, mock_anthropic_cls):
        mock_client = mock_anthropic_cls.return_value
        response = MagicMock()
        response.parsed_output = None
        mock_client.messages.parse.return_value = response

        ticket = Ticket(subject='x', description='y')
        with self.assertRaises(TriageError):
            triage_ticket(ticket)
