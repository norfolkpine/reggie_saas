from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.api.models import UserAPIKey

User = get_user_model()

class APIKeyAuthenticationTest(TestCase):
    def setUp(self):
        # Create system user and API key
        self.system_user = User.objects.create_user(
            email='cloud-run-service@system.local',
            password='testpass123',
            is_system=True
        )
        self.system_api_key = UserAPIKey.objects.create_key(
            name="Cloud Run Ingestion Service",
            user=self.system_user
        )
        
        # Create regular user and API key
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.user_api_key = UserAPIKey.objects.create_key(
            name="Test User API Key",
            user=self.user
        )
        
        self.client = APIClient()
        
    def test_system_api_key(self):
        """Test system API key authentication"""
        # Test with system API key
        self.client.credentials(HTTP_AUTHORIZATION=f'Api-Key {self.system_api_key[1]}')
        response = self.client.get(reverse('api:health'))
        self.assertEqual(response.status_code, 200)
        
    def test_user_api_key(self):
        """Test user API key authentication"""
        # Test with user API key
        self.client.credentials(HTTP_AUTHORIZATION=f'Api-Key {self.user_api_key[1]}')
        response = self.client.get(reverse('api:health'))
        self.assertEqual(response.status_code, 200)
        
    def test_invalid_api_key(self):
        """Test invalid API key"""
        self.client.credentials(HTTP_AUTHORIZATION='Api-Key invalid-key')
        response = self.client.get(reverse('api:health'))
        self.assertEqual(response.status_code, 403)
        
    def test_missing_api_key(self):
        """Test missing API key"""
        response = self.client.get(reverse('api:health'))
        self.assertEqual(response.status_code, 403)
        
    def test_wrong_prefix_format(self):
        """Test wrong API key prefix format"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user_api_key[1]}')
        response = self.client.get(reverse('api:health'))
        self.assertEqual(response.status_code, 403) 