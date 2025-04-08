from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from .views import (
    AgentExpectedOutputViewSet,
    AgentInstructionViewSet,
    AgentViewSet,
    DocumentTagViewSet,
    DocumentViewSet,
    GlobalExpectedOutputViewSet,
    GlobalInstructionViewSet,
    KnowledgeBaseViewSet,
    ProjectViewSet,
    StorageBucketViewSet,
    TagViewSet,
    ChatSessionViewSet,
    agent_request,
    get_agent_expected_output,
    get_agent_instructions,
    get_global_templates,
    slack_events,
    slack_oauth_callback,
    slack_oauth_start,
    stream_agent_response,
)

router = DefaultRouter()
router.register(r"agents", AgentViewSet, basename="agents")
router.register(r"instructions", AgentInstructionViewSet, basename="instructions")
router.register(r"expected-output", AgentExpectedOutputViewSet, basename="expected-output")
router.register(r"global-instructions", GlobalInstructionViewSet, basename="global-instructions")
router.register(r"global-outputs", GlobalExpectedOutputViewSet, basename="global-outputs")
router.register(r"storage-buckets", StorageBucketViewSet, basename="storage-buckets")
router.register(r"knowledge-bases", KnowledgeBaseViewSet, basename="knowledge-bases")
router.register(r"tags", TagViewSet, basename="tags")
router.register(r"projects", ProjectViewSet, basename="projects")
router.register(r"documents", DocumentViewSet, basename="documents")
router.register(r"document-tags", DocumentTagViewSet, basename="document-tags")
router.register(r"chat-sessions", ChatSessionViewSet, basename="chat-sessions")

# Versioned API routes
api_v1_patterns = [
    path("", include(router.urls)),
    # Unified global templates
    path("agent-templates/", get_global_templates, name="agent-templates"),
    # Agent-specific utils
    path("agent/<int:agent_id>/instructions/", get_agent_instructions, name="agent-instructions"),
    ## Showing all, needs fixing
    path("agent/<int:agent_id>/expected-output/", get_agent_expected_output, name="agent-output"),
    path("agent/<int:agent_id>/request/", agent_request, name="agent-request"),
    # NOT WORKING
    path("agent/stream-chat/", stream_agent_response, name="stream-agent-response"),
    # OpenAPI + Swagger
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

urlpatterns = [
    path("api/v1/", include((api_v1_patterns, "v1"), namespace="v1")),
    # Slack integration
    path("slack/events/", slack_events, name="slack-events"),
    path("slack/oauth/start/", slack_oauth_start, name="slack_oauth_start"),
    path("slack/oauth/callback/", slack_oauth_callback, name="slack_oauth_callback"),
]
