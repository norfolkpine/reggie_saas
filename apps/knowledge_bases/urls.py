from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KnowledgeBaseViewSet, KnowledgeBaseDocumentViewSet

router = DefaultRouter()
router.register(r'knowledge-bases', KnowledgeBaseViewSet, basename='knowledgebase')
router.register(r'kb-documents', KnowledgeBaseDocumentViewSet, basename='knowledgebasedocument') # Endpoint for managing docs within KBs

urlpatterns = [
    path('', include(router.urls)),
]
