from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.api.models import UserAPIKey

# from apps.users.models import CustomUser as User

User = get_user_model()


class APIKeyAuthenticationTest(TestCase):
    def setUp(self):
        # Create system user and API key
        self.system_user = User.objects.create_user(
            username="cloud-run-service", email="cloud-run-service@system.local", password="testpass123", is_device=True
        )
        self.system_api_key_obj, self.system_api_key = UserAPIKey.objects.create_key(
            name="Cloud Run Ingestion Service", user=self.system_user
        )

        # Create regular user and API key
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.user_api_key_obj, self.user_api_key = UserAPIKey.objects.create_key(
            name="Test User API Key", user=self.user
        )

        self.client = APIClient()

    def test_system_api_key(self):
        """Test system API key authentication"""
        # Test with system API key
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {self.system_api_key}")
        response = self.client.get(reverse("api:health"))
        self.assertEqual(response.status_code, 200)

    def test_user_api_key(self):
        """Test user API key authentication"""
        # Test with user API key
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {self.user_api_key}")
        response = self.client.get(reverse("api:health"))
        self.assertEqual(response.status_code, 200)

    def test_invalid_api_key(self):
        """Test invalid API key"""
        self.client.credentials(HTTP_AUTHORIZATION="Api-Key invalid-key")
        response = self.client.get(reverse("api:health"))
        self.assertEqual(response.status_code, 401)

    def test_missing_api_key(self):
        """Test missing API key"""
        response = self.client.get(reverse("api:health"))
        self.assertEqual(response.status_code, 401)

    def test_wrong_prefix_format(self):
        """Test wrong API key prefix format"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.user_api_key}")
        response = self.client.get(reverse("api:health"))
        self.assertEqual(response.status_code, 401)


class APIKeyManagementTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_api_key(self):
        """Test creating an API key"""
        url = reverse("users:create_api_key_json")
        response = self.client.post(url, {"name": "My Test Key"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIn("api_key", response.data)
        self.assertEqual(response.data["api_key"]["name"], "My Test Key")

    def test_list_api_keys(self):
        """Test listing API keys"""
        UserAPIKey.objects.create_key(name="Test Key 1", user=self.user)
        UserAPIKey.objects.create_key(name="Test Key 2", user=self.user)
        url = reverse("users:list_api_keys_json")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["count"], 2)

    def test_revoke_api_key(self):
        """Test revoking an API key"""
        api_key_obj, _ = UserAPIKey.objects.create_key(name="Test Key to Revoke", user=self.user)
        url = reverse("users:revoke_api_key_json")
        response = self.client.post(url, {"key_id": api_key_obj.id})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        api_key_obj.refresh_from_db()
        self.assertTrue(api_key_obj.revoked)

    def test_unauthenticated_access(self):
        """Test unauthenticated access to API key management endpoints"""
        self.client.logout()
        url = reverse("users:list_api_keys_json")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

        url = reverse("users:create_api_key_json")
        response = self.client.post(url, {"name": "My Test Key"})
        self.assertEqual(response.status_code, 401)

        url = reverse("users:revoke_api_key_json")
        response = self.client.post(url, {"key_id": 1})
        self.assertEqual(response.status_code, 401)
