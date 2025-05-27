import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import CustomUser as User


@pytest.mark.django_db
def test_login_view_json():
    # Create user for valid login
    User.objects.create_user(username="validuser", email="valid@example.com", password="validpass123")

    client = APIClient()
    url = reverse("authentication:rest_login")
    response = client.post(url, {"email": "valid@example.com", "password": "validpass123"}, format="json")

    assert response.status_code == 200
    data = response.json()
    assert "jwt" in data.get("jwt", {}) or "access" in data.get("jwt", {})  # depends on your wrapping


@pytest.mark.django_db
def test_login_with_invalid_email():
    # Create user
    User.objects.create_user(username="wrongemailuser", email="real@example.com", password="somepass123")

    client = APIClient()
    url = reverse("authentication:rest_login")
    response = client.post(url, {"email": "wrong@example.com", "password": "somepass123"}, format="json")

    assert response.status_code == 400
    data = response.json()
    assert "non_field_errors" in data or "detail" in data


@pytest.mark.django_db
def test_login_with_invalid_password():
    # Create user
    User.objects.create_user(username="wrongpassuser", email="user@example.com", password="correctpass")

    client = APIClient()
    url = reverse("authentication:rest_login")
    response = client.post(url, {"email": "user@example.com", "password": "wrongpass"}, format="json")

    assert response.status_code == 400
    data = response.json()
    assert "non_field_errors" in data or "detail" in data
