"""Fixtures for tests in the impress core application"""

from unittest import mock

import pytest
from django.core.cache import cache
from django.conf import settings
from apps.users.models import CustomUser

USER = "user"
TEAM = "team"
VIA = [USER, TEAM]

def pytest_configure():
    """Configure test settings."""
    settings.DEBUG = False
    # Ensure we're using a test database
    settings.DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'test_bh_reggie',
            'USER': settings.DATABASES['default']['USER'],
            'PASSWORD': settings.DATABASES['default']['PASSWORD'],
            'HOST': settings.DATABASES['default']['HOST'],
            'PORT': settings.DATABASES['default']['PORT'],
        }
    }

@pytest.fixture(autouse=True)
def clear_cache():
    """Fixture to clear the cache before each test."""
    cache.clear()


@pytest.fixture
def mock_user_teams():
    """Mock for team membership queries."""
    mock_queryset = mock.MagicMock()
    
    def values_list_side_effect(*args, **kwargs):
        if args[0] == "team_id" and kwargs.get("flat"):
            return ["lasuite", "unknown"]
        return mock_queryset
        
    mock_queryset.values_list = mock.MagicMock(side_effect=values_list_side_effect)
    
    with mock.patch("apps.teams.models.Membership.objects.filter", return_value=mock_queryset) as mock_teams:
        yield mock_teams
