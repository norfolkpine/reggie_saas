from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AgentViewSet, AgentInstructionViewSet, StorageBucketViewSet, KnowledgeBaseViewSet, 
    TagViewSet, ProjectViewSet, DocumentViewSet, DocumentTagViewSet, get_agent_instructions, slack_events, agent_request
)

router = DefaultRouter()
router.register(r'agents', AgentViewSet, basename='agents')
router.register(r'instructions', AgentInstructionViewSet, basename='instructions')
router.register(r'storage-buckets', StorageBucketViewSet, basename='storage-buckets')
router.register(r'knowledge-bases', KnowledgeBaseViewSet, basename='knowledge-bases')
router.register(r'tags', TagViewSet, basename='tags')
router.register(r'projects', ProjectViewSet, basename='projects')
router.register(r'documents', DocumentViewSet, basename='documents')
router.register(r'document-tags', DocumentTagViewSet, basename='document-tags')

urlpatterns = [
    path('api/', include(router.urls)),  # Bulk upload is now under /api/documents/bulk-upload/
    path("api/agents/<int:agent_id>/instructions/", get_agent_instructions, name="agent-instructions"),
     path("api/agent/<int:agent_id>/request/", agent_request, name="agent-request"),
]

urlpatterns += [
    path("slack/events/", slack_events, name="slack-events"),
]