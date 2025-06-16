import hashlib

from django.test import TestCase

from apps.users.models import CustomUser


class CustomUserGravatarTest(TestCase):
    def test_gravatar_id_falls_back_to_admin_email(self):
        user = CustomUser.objects.create(username="user1", admin_email="admin@example.com")
        expected = hashlib.md5("admin@example.com".encode("utf-8")).hexdigest()
        self.assertEqual(expected, user.gravatar_id)

    def test_gravatar_id_handles_missing_emails(self):
        user = CustomUser.objects.create(username="user2")
        expected = hashlib.md5(b"").hexdigest()
        self.assertEqual(expected, user.gravatar_id)
