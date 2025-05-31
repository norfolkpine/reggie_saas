from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from .models import KnowledgeBase, KnowledgeBaseDocument
from apps.docs.models import Document # Corrected import
from .serializers import KnowledgeBaseSerializer, KnowledgeBaseDocumentSerializer
# from .tasks import process_documents_for_kb  # To be used later

import uuid # For generating vector_store_id

class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Knowledge Bases to be viewed or edited.
    """
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [IsAuthenticated] # Adjust permissions as needed

    def get_queryset(self):
        # Filter queryset by owner if you want users to only see their KBs
        # For now, returning all for simplicity, but this should be user-scoped
        # return KnowledgeBase.objects.filter(owner=self.request.user)
        return KnowledgeBase.objects.all()

    def perform_create(self, serializer):
        # Generate a unique vector_store_id
        # This is a simple way; you might want a more robust/meaningful ID generation strategy
        vector_store_id = f"kb_{uuid.uuid4().hex[:16]}"
        # serializer.save(owner=self.request.user, vector_store_id=vector_store_id)
        kb = serializer.save(vector_store_id=vector_store_id) # Removed owner for now, can be added back

        # Placeholder: Trigger asynchronous task for document processing
        # This would typically involve getting document IDs from the request
        # and then fetching their content to pass to the task.
        # For now, let's assume document_ids are passed in request.data
        # document_ids = self.request.data.get('document_ids', [])
        # if document_ids:
        #     process_documents_for_kb.delay(kb.id, document_ids)
        # else:
        #     print(f"No document_ids provided for KB {kb.id}")


    @action(detail=True, methods=['post'], url_path='add-documents')
    def add_documents(self, request, pk=None):
        knowledge_base = self.get_object()
        document_ids = request.data.get('document_ids', [])

        if not document_ids:
            return Response({'error': 'No document_ids provided'}, status=status.HTTP_400_BAD_REQUEST)

        added_docs_count = 0
        errors = []

        for doc_id in document_ids:
            try:
                document = Document.objects.get(id=doc_id)
                _, created = KnowledgeBaseDocument.objects.get_or_create(
                    knowledge_base=knowledge_base,
                    document=document
                )
                if created:
                    added_docs_count += 1
            except Document.DoesNotExist:
                errors.append(f"Document with id {doc_id} not found.")
            except Exception as e:
                errors.append(f"Error adding document {doc_id}: {str(e)}")

        if errors:
            return Response({'message': f'{added_docs_count} documents added. Errors: {"; ".join(errors)}'}, status=status.HTTP_400_BAD_REQUEST if added_docs_count == 0 else status.HTTP_207_MULTI_STATUS)

        # Placeholder: Trigger re-indexing task
        # process_documents_for_kb.delay(knowledge_base.id, document_ids_to_reindex)

        return Response({'message': f'{added_docs_count} documents added successfully to {knowledge_base.name}. Re-indexing should be triggered.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='ask')
    def ask_question(self, request, pk=None):
        knowledge_base = self.get_object()
        question = request.data.get('question')

        if not question:
            return Response({'error': 'No question provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Placeholder for Q&A logic:
        # 1. Get vector_store_id from knowledge_base.vector_store_id
        # 2. Initialize/configure ReggieAgent with this vector_store_id
        #    (This might involve calling a method from agent_builder.py or a new QA agent class)
        # 3. agent.ask(question)
        # 4. Return answer and sources

        answer = f"This is a placeholder answer from KB '{knowledge_base.name}' for your question: '{question}'. Vector store ID: {knowledge_base.vector_store_id}"
        sources = [
            {"document_name": "Placeholder Doc 1", "snippet": "Relevant snippet from doc 1..."},
            {"document_name": "Placeholder Doc 2", "snippet": "Relevant snippet from doc 2..."}
        ]

        return Response({'answer': answer, 'sources': sources}, status=status.HTTP_200_OK)


class KnowledgeBaseDocumentViewSet(viewsets.ReadOnlyModelViewSet): # Or ModelViewSet if you allow direct manipulation
    """
    API endpoint for managing documents within a Knowledge Base.
    """
    queryset = KnowledgeBaseDocument.objects.all()
    serializer_class = KnowledgeBaseDocumentSerializer
    permission_classes = [IsAuthenticated] # Adjust as needed

    def get_queryset(self):
        # Filter by knowledge_base if provided in query_params
        kb_id = self.request.query_params.get('kb_id')
        if kb_id:
            return self.queryset.filter(knowledge_base_id=kb_id)
        # Potentially filter by user's KBs
        return self.queryset.filter(knowledge_base__owner=self.request.user) # Example, if owner is implemented

    # Add methods for removing documents from a KB if needed, which would also trigger re-indexing.
    # def perform_destroy(self, instance):
    #     kb = instance.knowledge_base
    #     super().perform_destroy(instance)
    #     # Trigger re-indexing for kb
    #     # process_documents_for_kb.delay(kb.id, [instance.document_id], action='remove')
    #     print(f"Document {instance.document.name} removed from KB {kb.name}. Re-indexing should be triggered.")

```
