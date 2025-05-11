import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_login_view(client):
    url = reverse('account_login')
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_with_invalid_credentials(client):
    url = reverse('account_login')
    response = client.post(url, {'login': 'invalid', 'password': 'invalid'})
    assert response.status_code == 200  # Typically returns 200 with an error message
    assert 'Please enter a correct username and password.' in response.content.decode() 