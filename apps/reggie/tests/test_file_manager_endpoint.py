"""
Test the updated file manager endpoint that includes current_collection and breadcrumb_path.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.reggie.models import Collection
from apps.users.models import CustomUser


@pytest.mark.django_db
class TestFileManagerEndpoint:
    """Test the file manager endpoint with new fields."""

    def setup_method(self):
        """Set up test data."""
        self.client = APIClient()

        # Create test user
        self.user = CustomUser.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client.force_authenticate(user=self.user)

        # Create test collections
        self.root_collection = Collection.objects.create(
            name="Root Documents", description="Root level documents", collection_type="folder"
        )

        self.sub_collection = Collection.objects.create(
            name="Sub Folder",
            description="Sub folder for testing",
            parent=self.root_collection,
            collection_type="folder",
        )

        self.deep_collection = Collection.objects.create(
            name="Deep Folder", description="Deep nested folder", parent=self.sub_collection, collection_type="folder"
        )

    def test_file_manager_root_level(self):
        """Test file manager endpoint at root level."""
        url = reverse("api:file-list")
        response = self.client.get(url, {"file_manager": "true"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check that new fields are present
        assert "current_collection" in data
        assert "breadcrumb_path" in data

        # Check root level current_collection
        current_collection = data["current_collection"]
        assert current_collection["uuid"] is None
        assert current_collection["name"] == "Root"
        assert current_collection["description"] == "Root directory"
        assert current_collection["collection_type"] == "folder"
        assert current_collection["created_at"] is None

        # Check root level breadcrumb
        breadcrumb = data["breadcrumb_path"]
        assert len(breadcrumb) == 1
        assert breadcrumb[0]["uuid"] is None
        assert breadcrumb[0]["name"] == "Root"

        # Check standard fields
        assert "count" in data
        assert "results" in data
        assert "next" in data
        assert "previous" in data

    def test_file_manager_with_collection_uuid(self):
        """Test file manager endpoint with specific collection UUID."""
        url = reverse("api:file-list")
        response = self.client.get(url, {"file_manager": "true", "collection_uuid": str(self.sub_collection.uuid)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check current_collection for sub_collection
        current_collection = data["current_collection"]
        assert current_collection["uuid"] == str(self.sub_collection.uuid)
        assert current_collection["name"] == self.sub_collection.name
        assert current_collection["description"] == self.sub_collection.description
        assert current_collection["collection_type"] == self.sub_collection.collection_type
        assert current_collection["created_at"] is not None

        # Check breadcrumb path (Root -> Sub Folder)
        breadcrumb = data["breadcrumb_path"]
        assert len(breadcrumb) == 2
        assert breadcrumb[0]["uuid"] is None
        assert breadcrumb[0]["name"] == "Root"
        assert breadcrumb[1]["uuid"] == str(self.sub_collection.uuid)
        assert breadcrumb[1]["name"] == self.sub_collection.name

    def test_file_manager_deep_nested_collection(self):
        """Test file manager endpoint with deeply nested collection."""
        url = reverse("api:file-list")
        response = self.client.get(url, {"file_manager": "true", "collection_uuid": str(self.deep_collection.uuid)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check current_collection for deep_collection
        current_collection = data["current_collection"]
        assert current_collection["uuid"] == str(self.deep_collection.uuid)
        assert current_collection["name"] == self.deep_collection.name

        # Check breadcrumb path (Root -> Sub Folder -> Deep Folder)
        breadcrumb = data["breadcrumb_path"]
        assert len(breadcrumb) == 3
        assert breadcrumb[0]["uuid"] is None
        assert breadcrumb[0]["name"] == "Root"
        assert breadcrumb[1]["uuid"] == str(self.sub_collection.uuid)
        assert breadcrumb[1]["name"] == self.sub_collection.name
        assert breadcrumb[2]["uuid"] == str(self.deep_collection.uuid)
        assert breadcrumb[2]["name"] == self.deep_collection.name

    def test_file_manager_without_file_manager_param(self):
        """Test that regular file listing still works without file_manager param."""
        url = reverse("api:file-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should not have the new fields
        assert "current_collection" not in data
        assert "breadcrumb_path" not in data

        # Should have standard fields
        assert "count" in data
        assert "results" in data

    def test_file_manager_collection_not_found(self):
        """Test file manager with non-existent collection UUID."""
        url = reverse("api:file-list")
        response = self.client.get(url, {"file_manager": "true", "collection_uuid": "00000000-0000-0000-0000-000000000000"})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "error" in data
        assert "Collection not found" in data["error"]
