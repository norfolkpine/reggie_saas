import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_login_view(client):
    url = reverse('account_login')
    response = client.get(url)
    assert response.status_code == 200
    # Check for a specific element or text in the HTML
    assert '<form' in response.content.decode()  # Example: Check if a form is present


@pytest.mark.django_db
def test_login_with_invalid_credentials(client):
    url = reverse('account_login')
    response = client.post(url, {'login': 'invalid', 'password': 'invalid'}, content_type='application/json')
    assert response.status_code == 400  # Typically returns 400 for bad request
    assert 'non_field_errors' in response.json()  # Check for specific error in JSON response 
