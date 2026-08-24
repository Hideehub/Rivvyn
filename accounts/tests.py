from django.test import TestCase
from django.urls import reverse

from .models import User


class SignUpTests(TestCase):
    def test_signup_creates_customer_and_logs_in(self):
        response = self.client.post(reverse('signup'), {
            'username': 'carol',
            'email': 'carol@example.com',
            'password1': 'S0meStrongPass!23',
            'password2': 'S0meStrongPass!23',
        }, follow=True)

        user = User.objects.get(username='carol')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.is_customer)
        self.assertRedirects(response, reverse('home'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_signup_cannot_set_role_via_post_data(self):
        self.client.post(reverse('signup'), {
            'username': 'mallory',
            'email': 'mallory@example.com',
            'password1': 'S0meStrongPass!23',
            'password2': 'S0meStrongPass!23',
            'role': User.Role.AGENT,
        })
        user = User.objects.get(username='mallory')
        self.assertEqual(user.role, User.Role.CUSTOMER)


class HomeViewTests(TestCase):
    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_customer_sees_ticket_submission_placeholder(self):
        user = User.objects.create_user(username='carol', password='pw', role=User.Role.CUSTOMER)
        self.client.force_login(user)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Ticket submission')

    def test_agent_sees_dashboard_placeholder(self):
        agent = User.objects.create_user(username='dave', password='pw', role=User.Role.AGENT)
        self.client.force_login(agent)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'agent dashboard')
