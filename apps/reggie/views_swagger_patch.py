from drf_spectacular.utils import extend_schema

from .serializers import KnowledgeBaseSerializer


def patch_knowledgebaseviewset_create(viewset_cls):
    orig_create = viewset_cls.create

    @extend_schema(
        summary="Create a knowledge base",
        description="Create a new knowledge base. Optionally share it with teams by providing a list of permission objects (team_id and role).",
        request=KnowledgeBaseSerializer,
        responses={201: KnowledgeBaseSerializer},
    )
    def wrapped_create(self, request, *args, **kwargs):
        return orig_create(self, request, *args, **kwargs)

    viewset_cls.create = wrapped_create


# Usage: in your app config or ready() call
# from .views import KnowledgeBaseViewSet
# from .views_swagger_patch import patch_knowledgebaseviewset_create
# patch_knowledgebaseviewset_create(KnowledgeBaseViewSet)
