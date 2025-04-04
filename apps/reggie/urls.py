from django.urls import path, include
from rest_framework.routers import DefaultRouter
# At the top
from .views import (
    AgentViewSet, AgentInstructionViewSet, AgentExpectedOutputViewSet, StorageBucketViewSet, KnowledgeBaseViewSet, 
    TagViewSet, ProjectViewSet, DocumentViewSet, DocumentTagViewSet, get_agent_instructions, get_agent_expected_output, slack_events, agent_request,
    slack_oauth_start, slack_oauth_callback, stream_agent_response
)

router = DefaultRouter()
router.register(r'agents', AgentViewSet, basename='agents')
router.register(r'instructions', AgentInstructionViewSet, basename='instructions')
router.register(r'expected-output', AgentExpectedOutputViewSet, basename='expected-output')
router.register(r'storage-buckets', StorageBucketViewSet, basename='storage-buckets')
router.register(r'knowledge-bases', KnowledgeBaseViewSet, basename='knowledge-bases')
router.register(r'tags', TagViewSet, basename='tags')
router.register(r'projects', ProjectViewSet, basename='projects')
router.register(r'documents', DocumentViewSet, basename='documents')
router.register(r'document-tags', DocumentTagViewSet, basename='document-tags')

urlpatterns = [
    path('api/', include(router.urls)),  # Bulk upload is now under /api/documents/bulk-upload/
    path("api/agents/<int:agent_id>/instructions/", get_agent_instructions, name="agent-instructions"),
    path("api/agents/<int:agent_id>/expected-output/", get_agent_expected_output, name="agent-output"),
    path("api/agent/<int:agent_id>/request/", agent_request, name="agent-request"),
    path("api/agents/stream-chat/", stream_agent_response, name="stream-agent-response"),
]

# Slack URL's
urlpatterns += [
    path("slack/events/", slack_events, name="slack-events"),
]
urlpatterns += [
    path("slack/oauth/start/", slack_oauth_start, name="slack_oauth_start"),
    path("slack/oauth/callback/", slack_oauth_callback, name="slack_oauth_callback"),
]