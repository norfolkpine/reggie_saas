from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IntegrationViewSet

router = DefaultRouter()
router.register(r"integrations", IntegrationViewSet, basename='integration')

# Define the API v1 patterns for this app
api_v1_patterns = [
    path("", include(router.urls)),
]

# Keep urlpatterns for non-API views if any, otherwise it can be empty or removed
urlpatterns = [
    # Add any non-API specific urls here if needed
]