from django.test import TestCase
from django.conf import settings as django_settings # To avoid conflict with @patch target
from unittest.mock import patch, MagicMock
import uuid

from apps.users.models import CustomUser
from apps.reggie.models import Project, File, KnowledgeBase, FileKnowledgeBaseLink, ModelProvider
from apps.reggie.utils.gcs_utils import ingest_single_file

# For creating dummy files
from django.core.files.uploadedfile import SimpleUploadedFile

class IngestSingleFileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uploader_user = CustomUser.objects.create_user(username='uploader_gcs', email='uploader_gcs@test.com', password='password123')

        cls.project_linked = Project.objects.create(name='Project For GCS Test', owner=cls.uploader_user)

        cls.model_provider = ModelProvider.objects.create(provider="test_gcs_provider", model_name="test_gcs_model", embedder_id="test_gcs_embedder")

        cls.kb = KnowledgeBase.objects.create(
            name="KB for GCS Test",
            owner=cls.uploader_user,
            model_provider=cls.model_provider,
            chunk_size=1000,
            chunk_overlap=200
        )

        # Dummy file content
        dummy_file_content = b"This is a dummy file for GCS util testing."

        # File linked to a project
        cls.file_with_project = File.objects.create(
            uuid=uuid.uuid4(),
            title="file_with_project.txt",
            uploaded_by=cls.uploader_user,
            vault_project=cls.project_linked,
            file=SimpleUploadedFile("file_with_project.txt", dummy_file_content, content_type="text/plain")
        )
        cls.link_to_file_with_project = FileKnowledgeBaseLink.objects.create(
            file=cls.file_with_project,
            knowledge_base=cls.kb
        )

        # File NOT linked to a project
        cls.file_without_project = File.objects.create(
            uuid=uuid.uuid4(),
            title="file_without_project.txt",
            uploaded_by=cls.uploader_user,
            vault_project=None, # Explicitly None
            file=SimpleUploadedFile("file_without_project.txt", dummy_file_content, content_type="text/plain")
        )
        cls.link_to_file_without_project = FileKnowledgeBaseLink.objects.create(
            file=cls.file_without_project,
            knowledge_base=cls.kb
        )

        # Store original settings to restore them if necessary, though @patch should handle this for specific tests
        cls.original_llama_url = getattr(django_settings, 'LLAMAINDEX_INGESTION_URL', 'http://default-url')
        cls.original_api_key = getattr(django_settings, 'DJANGO_API_KEY_FOR_LLAMAINDEX', None)


    @patch('apps.reggie.utils.gcs_utils.settings', LLAMAINDEX_INGESTION_URL='http://fake-ingestion-url', DJANGO_API_KEY_FOR_LLAMAINDEX='fakekey', DEBUG=True)
    @patch('apps.reggie.utils.gcs_utils.requests.post')
    def test_ingest_single_file_with_project_id(self, mock_post, mock_settings):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Ingestion started"}
        mock_post.return_value = mock_response

        ingest_single_file(
            file_path=f"gs://test-bucket/{self.file_with_project.file.name}", # Path format as expected by func
            vector_table_name=self.kb.vector_table_name,
            file_uuid=str(self.file_with_project.uuid),
            link_id=self.link_to_file_with_project.id,
            embedding_provider=self.kb.model_provider.provider,
            embedding_model=self.kb.model_provider.embedder_id,
            chunk_size=self.kb.chunk_size,
            chunk_overlap=self.kb.chunk_overlap
        )

        mock_post.assert_called_once()
        called_payload = mock_post.call_args[1]['json']
        self.assertIn('project_id', called_payload)
        self.assertEqual(called_payload['project_id'], str(self.project_linked.uuid))
        self.assertEqual(called_payload['file_uuid'], str(self.file_with_project.uuid))


    @patch('apps.reggie.utils.gcs_utils.settings', LLAMAINDEX_INGESTION_URL='http://fake-ingestion-url', DJANGO_API_KEY_FOR_LLAMAINDEX='fakekey', DEBUG=True)
    @patch('apps.reggie.utils.gcs_utils.requests.post')
    def test_ingest_single_file_without_project_id(self, mock_post, mock_settings):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Ingestion started"}
        mock_post.return_value = mock_response

        ingest_single_file(
            file_path=f"gs://test-bucket/{self.file_without_project.file.name}",
            vector_table_name=self.kb.vector_table_name,
            file_uuid=str(self.file_without_project.uuid),
            link_id=self.link_to_file_without_project.id,
            embedding_provider=self.kb.model_provider.provider,
            embedding_model=self.kb.model_provider.embedder_id,
            chunk_size=self.kb.chunk_size,
            chunk_overlap=self.kb.chunk_overlap
        )

        mock_post.assert_called_once()
        called_payload = mock_post.call_args[1]['json']
        self.assertNotIn('project_id', called_payload) # project_id should not be in the payload
        self.assertEqual(called_payload['file_uuid'], str(self.file_without_project.uuid))

    @patch('apps.reggie.utils.gcs_utils.settings', LLAMAINDEX_INGESTION_URL='http://fake-ingestion-url', DJANGO_API_KEY_FOR_LLAMAINDEX='fakekey', DEBUG=True)
    @patch('apps.reggie.utils.gcs_utils.requests.post')
    @patch('apps.reggie.utils.gcs_utils.logger.error') # Mock logger.error
    def test_ingest_single_file_non_existent_uuid(self, mock_logger_error, mock_post, mock_settings):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Ingestion started"} # This response will be used if post is called
        mock_post.return_value = mock_response

        non_existent_uuid = str(uuid.uuid4())

        ingest_single_file(
            file_path="gs://test-bucket/some_file.txt",
            vector_table_name=self.kb.vector_table_name,
            file_uuid=non_existent_uuid, # Non-existent
            link_id=999, # Dummy link_id
            embedding_provider=self.kb.model_provider.provider,
            embedding_model=self.kb.model_provider.embedder_id,
            chunk_size=self.kb.chunk_size,
            chunk_overlap=self.kb.chunk_overlap
        )

        # The function should log an error and then proceed to call post (payload won't have project_id)
        # because the current implementation logs File.DoesNotExist but still proceeds.
        mock_logger_error.assert_any_call(f"File with uuid {non_existent_uuid} not found during ingestion. Cannot determine project_id.")

        # requests.post should still be called, but project_id will be missing from payload
        mock_post.assert_called_once()
        called_payload = mock_post.call_args[1]['json']
        self.assertNotIn('project_id', called_payload)
        self.assertEqual(called_payload['file_uuid'], non_existent_uuid)


    @patch('apps.reggie.utils.gcs_utils.settings', LLAMAINDEX_INGESTION_URL='http://fake-ingestion-url', DJANGO_API_KEY_FOR_LLAMAINDEX='fakekey', DEBUG=True)
    @patch('apps.reggie.utils.gcs_utils.requests.post')
    def test_ingest_single_file_no_file_uuid_provided(self, mock_post, mock_settings):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Ingestion started"}
        mock_post.return_value = mock_response

        ingest_single_file(
            file_path="gs://test-bucket/another_file.txt",
            vector_table_name=self.kb.vector_table_name,
            file_uuid=None, # No file_uuid
            link_id=self.link_to_file_without_project.id, # Using a valid link for other params
            embedding_provider=self.kb.model_provider.provider,
            embedding_model=self.kb.model_provider.embedder_id,
            chunk_size=self.kb.chunk_size,
            chunk_overlap=self.kb.chunk_overlap
        )

        mock_post.assert_called_once()
        called_payload = mock_post.call_args[1]['json']
        self.assertNotIn('project_id', called_payload) # No project_id because no file_uuid to fetch File
        self.assertNotIn('file_uuid', called_payload) # file_uuid itself should not be in payload if None
```
