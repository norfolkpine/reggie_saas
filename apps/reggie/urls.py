from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.slack_integration.views.events import slack_events
from apps.slack_integration.views.oauth import (
    slack_oauth_callback,
    slack_oauth_start,
)

from .views import (
    AgentExpectedOutputViewSet,
    AgentInstructionViewSet,
    AgentViewSet,
    CategoryViewSet,
    ChatSessionViewSet,
    FileTagViewSet,
    FileViewSet,
    GlobalExpectedOutputViewSet,
    GlobalInstructionViewSet,
    KnowledgeBasePdfURLViewSet,
    KnowledgeBaseViewSet,
    ModelProviderViewSet,
    ProjectViewSet,
    StorageBucketViewSet,
    TagViewSet,
    UserFeedbackViewSet,
    VaultFileViewSet,
    agent_request,
    get_agent_expected_output,
    get_agent_instructions,
    get_global_templates,
)

router = DefaultRouter()
router.register(r"agents", AgentViewSet, basename="agents")
router.register(r"user-feedback", UserFeedbackViewSet, basename="user-feedback")
router.register(r"instructions", AgentInstructionViewSet, basename="instructions")
router.register(r"expected-output", AgentExpectedOutputViewSet, basename="expected-output")
router.register(r"global-instructions", GlobalInstructionViewSet, basename="global-instructions")
router.register(r"global-outputs", GlobalExpectedOutputViewSet, basename="global-outputs")
router.register(r"storage-buckets", StorageBucketViewSet, basename="storage-buckets")
router.register(r"knowledge-bases", KnowledgeBaseViewSet, basename="knowledge-bases")
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"tags", TagViewSet, basename="tags")
router.register(r"projects", ProjectViewSet, basename="projects")
router.register(r"files", FileViewSet, basename="files")
router.register(r"vault-files", VaultFileViewSet, basename="vault-files")  # endpoint vault-files
router.register(r"file-tags", FileTagViewSet, basename="file-tags")
router.register(r"chat-sessions", ChatSessionViewSet, basename="chat-sessions")
router.register(r"model-providers", ModelProviderViewSet, basename="model-providers")
router.register(r"knowledge-base/pdf-urls", KnowledgeBasePdfURLViewSet, basename="kb-pdf-urls")

# API versioning patterns
api_v1_patterns = [
    path("", include(router.urls)),
    # Agent endpoints
    path(
        "agents/<int:agent_id>/",
        include(
            [
                path("instructions/", get_agent_instructions, name="agent-instructions"),
                path("expected-output/", get_agent_expected_output, name="agent-output"),
                path("request/", agent_request, name="agent-request"),
            ]
        ),
    ),
    # Templates
    path("templates/", get_global_templates, name="agent-templates"),
    # Chat - now handled by Django Channels - see apps/reggie/routing.py
    # path("chat/stream/", stream_agent_response, name="stream-agent-response"),
    # Files
    # path("files/ingestion-status/", include(router.urls)),  # Removed - causing operationId collision
    path(
        "files/<uuid:uuid>/update-progress/",
        FileViewSet.as_view({"post": "update_progress"}),
        name="file-update-progress",
    ),
    # Documentation
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

# Integration endpoints
integration_patterns = [
    path(
        "slack/",
        include(
            [
                path("events/", slack_events, name="slack-events"),
                path(
                    "oauth/",
                    include(
                        [
                            path("start/", slack_oauth_start, name="slack_oauth_start"),
                            path("callback/", slack_oauth_callback, name="slack_oauth_callback"),
                        ]
                    ),
                ),
            ]
        ),
    ),
]

urlpatterns = [
    path("api/v1/", include((api_v1_patterns, "v1"), namespace="v1")),
    path("integrations/", include((integration_patterns, "integrations"), namespace="integrations")),
]
