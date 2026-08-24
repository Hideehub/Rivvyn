from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import Ticket, TicketNote


class TicketCreateViewTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        self.client.force_login(self.customer)

    def test_submit_ticket_sets_customer_and_defaults(self):
        response = self.client.post(reverse('tickets:create'), {
            'subject': 'Cannot log in',
            'description': 'I get an error when I try to log in.',
        })
        ticket = Ticket.objects.get(subject='Cannot log in')
        self.assertEqual(ticket.customer, self.customer)
        self.assertEqual(ticket.status, Ticket.Status.OPEN)
        self.assertEqual(ticket.category, '')
        self.assertRedirects(response, reverse('tickets:detail', args=[ticket.pk]))

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
