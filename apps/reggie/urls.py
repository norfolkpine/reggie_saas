from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AgentViewSet, AgentInstructionViewSet

router = DefaultRouter()
router.register(r'agents', AgentViewSet)
router.register(r'instructions', AgentInstructionViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
