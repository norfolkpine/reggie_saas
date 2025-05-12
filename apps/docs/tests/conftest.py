"""Fixtures for tests in the impress core application"""

from unittest import mock

import pytest
from django.core.cache import cache
from django.conf import settings
from django.db import connection
from django.core.files.storage import default_storage
from apps.users.models import CustomUser

USER = "user"
TEAM = "team"
VIA = [USER, TEAM]

def pytest_configure():
    """Configure test settings."""
    settings.DEBUG = False
    # Use the existing database configuration but ensure test settings are properly set
    test_settings = settings.DATABASES['default'].copy()
    # Preserve any existing TEST settings if they exist
    test_settings['TEST'] = settings.DATABASES['default'].get('TEST', {})
    
    settings.DATABASES = {
        'default': test_settings
    }

@pytest.fixture(autouse=True)
def clear_cache():
    """Fixture to clear the cache before each test."""
    cache.clear()

@pytest.fixture(autouse=True)
def _db_cleanup(django_db_setup, django_db_blocker):
    """Ensure database is clean before each test."""
    with django_db_blocker.unblock():
        connection.cursor().execute("""
            TRUNCATE TABLE impress_document CASCADE;
        """)
        yield

@pytest.fixture(autouse=True)
def mock_storage():
    """Mock cloud storage operations."""
    mock_client = mock.MagicMock()
    mock_bucket = mock.MagicMock()
    mock_blob = mock.MagicMock()
    
    # Mock common storage operations
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    mock_blob.exists.return_value = True
    
    # Mock metadata operations
    mock_head = {
        "Metadata": {},
        "ContentType": "application/octet-stream",
        "ContentDisposition": "inline"
    }
    mock_client.head_object.return_value = mock_head
    
    # Mock list operations
    mock_versions = {
        "Versions": [{"Key": "test-key", "VersionId": "1"}]
    }
    mock_client.list_object_versions.return_value = mock_versions
    
    # Mock the connection.meta.client on default_storage
    with mock.patch.object(default_storage, 'connection') as mock_conn:
        mock_conn.meta.client = mock_client
        yield mock_client

@pytest.fixture
def mock_user_teams():
    """Mock for team membership queries."""
    mock_queryset = mock.MagicMock()
    mock_filtered = mock.MagicMock()
    
    def filter_side_effect(*args, **kwargs):
        return mock_filtered
        
    def values_list_side_effect(*args, **kwargs):
        if args[0] == "team_id" and kwargs.get("flat"):
            return ["lasuite", "unknown"]
        return mock_filtered
        
    mock_filtered.values_list = mock.MagicMock(side_effect=values_list_side_effect)
    mock_queryset.filter = mock.MagicMock(side_effect=filter_side_effect)
    
    with mock.patch("apps.teams.models.Membership.objects.filter", return_value=mock_queryset) as mock_teams:
        yield mock_teams
