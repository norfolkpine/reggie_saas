from rest_framework import viewsets, generics, permissions
from rest_framework.response import Response
from .models import (
    Agent, AgentInstruction, StorageBucket, KnowledgeBase, Tag, Project, Document, DocumentTag
)
from .serializers import (
    AgentSerializer, AgentInstructionSerializer, StorageBucketSerializer, KnowledgeBaseSerializer, 
    TagSerializer, ProjectSerializer, DocumentSerializer, DocumentTagSerializer, BulkDocumentUploadSerializer
)


class AgentViewSet(viewsets.ModelViewSet):
    queryset = Agent.objects.all()
    serializer_class = AgentSerializer
    permission_classes = [permissions.IsAuthenticated]


class AgentInstructionViewSet(viewsets.ModelViewSet):
    queryset = AgentInstruction.objects.all()
    serializer_class = AgentInstructionSerializer
    permission_classes = [permissions.IsAuthenticated]


class StorageBucketViewSet(viewsets.ModelViewSet):
    queryset = StorageBucket.objects.all()
    serializer_class = StorageBucketSerializer
    permission_classes = [permissions.IsAuthenticated]


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [permissions.IsAuthenticated]


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class DocumentTagViewSet(viewsets.ModelViewSet):
    queryset = DocumentTag.objects.all()
    serializer_class = DocumentTagSerializer
    permission_classes = [permissions.IsAuthenticated]


class BulkDocumentUploadView(generics.CreateAPIView):
    serializer_class = BulkDocumentUploadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documents = serializer.save()
        return Response({"message": f"{len(documents)} documents uploaded successfully."})
