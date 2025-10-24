from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PersonViewSet, DocumentViewSet, ActionLogViewSet

router = DefaultRouter()
router.register(r'persons', PersonViewSet)
router.register(r'documents', DocumentViewSet)
router.register(r'action-logs', ActionLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
