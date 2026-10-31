import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class SettingsSecretKeyTests(SimpleTestCase):
    """Imports rivyn.settings in a fresh process, so each case sees its own env.
    Variables set here win over .env, because load_dotenv never overrides."""

    def _import_settings(self, **env):
        return subprocess.run(
            [sys.executable, '-c', 'import rivyn.settings as s; print(s.DEBUG, s.SECRET_KEY)'],
            cwd=settings.BASE_DIR,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
        )

    def test_missing_secret_key_without_debug_refuses_to_start(self):
        result = self._import_settings(DJANGO_DEBUG='False', DJANGO_SECRET_KEY='')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)

    def test_secret_key_from_env_without_debug(self):
        result = self._import_settings(DJANGO_DEBUG='False', DJANGO_SECRET_KEY='from-the-environment')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'False from-the-environment')

    def test_debug_falls_back_to_dev_key(self):
        result = self._import_settings(DJANGO_DEBUG='True', DJANGO_SECRET_KEY='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'True django-insecure-dev-only-change-me')
