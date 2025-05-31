from rest_framework import serializers
from .models import KnowledgeBase, KnowledgeBaseDocument
from apps.docs.models import Document # Ensure this import is correct

class KnowledgeBaseDocumentSerializer(serializers.ModelSerializer):
    document_name = serializers.CharField(source='document.name', read_only=True)
    document_id = serializers.UUIDField(source='document.id', write_only=True)

    class Meta:
        model = KnowledgeBaseDocument
        fields = ['id', 'knowledge_base', 'document', 'document_id', 'document_name', 'added_at']
        read_only_fields = ['id', 'knowledge_base', 'document', 'added_at'] # 'document' is read_only as it's set via document_id

    def create(self, validated_data):
        # The view will handle associating the document via document_id
        # This serializer might be more for reading, or for nested creation if customized
        return super().create(validated_data)

class KnowledgeBaseSerializer(serializers.ModelSerializer):
    # documents = KnowledgeBaseDocumentSerializer(many=True, read_only=True, source='kb_documents')
    # Or, if you want to allow adding documents by ID during KB creation/update:
    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        help_text="List of document UUIDs to associate with this Knowledge Base."
    )
    owner_username = serializers.CharField(source='owner.username', read_only=True, allow_null=True)


    class Meta:
        model = KnowledgeBase
        fields = [
            'id', 'name', 'owner', 'owner_username', 'vector_store_id',
            'created_at', 'updated_at', 'document_ids' # 'documents'
        ]
        read_only_fields = ['id', 'vector_store_id', 'created_at', 'updated_at', 'owner']

    def create(self, validated_data):
        document_ids = validated_data.pop('document_ids', [])
        # owner = self.context['request'].user # Assuming owner is set from request context in view
        # knowledge_base = KnowledgeBase.objects.create(owner=owner, **validated_data)
        knowledge_base = KnowledgeBase.objects.create(**validated_data) # Owner removed for now

        for doc_id in document_ids:
            try:
                document = Document.objects.get(id=doc_id)
                KnowledgeBaseDocument.objects.create(knowledge_base=knowledge_base, document=document)
            except Document.DoesNotExist:
                # Handle or log error: document not found
                print(f"Warning: Document with id {doc_id} not found during KB creation.")
                pass
        return knowledge_base

    def update(self, instance, validated_data):
        document_ids = validated_data.pop('document_ids', None) # Use None to detect if field was provided

        instance = super().update(instance, validated_data)

        if document_ids is not None: # Only update if document_ids was actually passed
            # Clear existing documents and add new ones, or implement more sophisticated diffing
            # For simplicity, let's replace:
            instance.kb_documents.all().delete()
            for doc_id in document_ids:
                try:
                    document = Document.objects.get(id=doc_id)
                    KnowledgeBaseDocument.objects.create(knowledge_base=instance, document=document)
                except Document.DoesNotExist:
                    print(f"Warning: Document with id {doc_id} not found during KB update.")
                    pass
        return instance
