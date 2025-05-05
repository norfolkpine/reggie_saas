# Create your tests here.

import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_api_key.models import APIKey

from apps.api.models import UserAPIKey

from .models import File

User = get_user_model()


class FileAPIKeyAuthenticationTest(APITestCase):
    def setUp(self):
        # Create system user and API key
        self.system_user = User.objects.create_user(
            email="cloud-run-service@system.local", password="testpass123", is_system=True
        )
        self.system_api_key, self.system_key = APIKey.objects.create_key(name="Cloud Run Ingestion Service")

        # Create regular user and API key
        self.user = User.objects.create_user(email="test@example.com", password="testpass123")
        self.user_api_key = UserAPIKey.objects.create_key(name="Test User API Key", user=self.user)

        # Create a test file
        self.file_uuid = uuid.uuid4()
        self.file = File.objects.create(uuid=self.file_uuid, title="Test File", file_type="pdf")

        self.update_url = reverse("files-update-progress", kwargs={"uuid": self.file_uuid})
        self.list_url = reverse("files-list-with-kbs")

    def test_update_progress_with_system_api_key(self):
        """Test that update_progress endpoint works with valid system API key"""
        headers = {"Authorization": f"Api-Key {self.system_key}"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_update_progress_with_user_api_key_fails(self):
        """Test that update_progress endpoint fails with user API key"""
        headers = {"Authorization": f"Api-Key {self.user_api_key[1]}"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_list_files_with_system_api_key(self):
        """Test that list endpoint works with system API key"""
        headers = {"Authorization": f"Api-Key {self.system_key}"}
        response = self.client.get(self.list_url, format="json", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_list_files_with_user_api_key(self):
        """Test that list endpoint works with user API key"""
        headers = {"Authorization": f"Api-Key {self.user_api_key[1]}"}
        response = self.client.get(self.list_url, format="json", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_update_progress_with_invalid_api_key(self):
        """Test that update_progress endpoint fails with invalid API key"""
        headers = {"Authorization": "Api-Key invalid-key"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_update_progress_with_wrong_prefix(self):
        """Test that update_progress endpoint fails with wrong Authorization prefix"""
        headers = {"Authorization": f"Bearer {self.system_key}"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid API key format", str(response.content))
