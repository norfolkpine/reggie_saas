import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

# Adjust path to import 'main' from the parent directory if 'tests' is a subdirectory
# If test_main.py is in the same directory as main.py, this specific adjustment might not be needed,
# but it's safer if tests are run from a different root.
# Assuming 'cloudrun/bh-reggie-llamaindex/' is the directory containing 'main.py'
# and this test file is also inside it.
# If tests are run from the project root, 'cloudrun.bh-reggie-llamaindex.main' might be the import path.

# We will patch load_env first, then import main and its app
# This ensures that when main.py is imported, its load_env call is already mocked.

# --- Start Patching load_env ---
# This has to be done *before* 'from main import app'
# if main.py calls load_env() at the module level.
# Create a mock object for load_env
mock_load_env = MagicMock()

# Apply the patch to 'main.load_env'
# The string 'main.load_env' assumes that 'main.py' will be importable as 'main'.
# This requires that the directory containing 'main.py' is in sys.path.
# If test_main.py is in the same directory as main.py, Python's default import mechanism
# should allow 'import main' if the tests are run from that directory.
# If run from a project root, you might need 'from cloudrun.bh-reggie-llamaindex import main'
# and patch 'cloudrun.bh-reggie-llamaindex.main.load_env'.

# For simplicity, assuming the test runner or PYTHONPATH is set up so 'main' can be imported.
# If you run `python -m unittest test_main.py` from within the `bh-reggie-llamaindex` directory,
# `import main` and patching `main.load_env` should work.

# If running from a higher-level directory (e.g. project root):
# Option 1: Add the directory to sys.path before importing main
# current_dir = os.path.dirname(os.path.abspath(__file__))
# main_py_dir = current_dir # If test_main.py is in the same dir as main.py
# sys.path.insert(0, main_py_dir) # Add to front of path

# Option 2: Use the full path if importing from a package structure
# e.g., from cloudrun.bh_reggie_llamaindex.main import app
# and patch 'cloudrun.bh_reggie_llamaindex.main.load_env'

# Let's assume the simpler case for now: test is run from the same directory as main.py
# or PYTHONPATH is configured.
patcher_load_env = patch('main.load_env', mock_load_env)
patcher_load_env.start()

# Now that load_env is patched, we can import main and app
from main import app, FileIngestRequest # Import app and any Pydantic models if needed for direct use
from llama_index.core import Document as LlamaDocument # For creating mock LlamaIndex documents

# --- End Patching load_env ---


class TestIngestionService(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        # It's good practice to ensure required env vars for Pydantic models in main.py are set
        # if load_env mock doesn't cover them or if they are accessed directly.
        # However, since load_env is mocked, it shouldn't try to load .env or access GCP secrets.
        # We might need to set some os.environ variables if main.py reads them at module level
        # *after* the load_env call for configuration.
        # For this test, we assume main.py is structured such that critical env var access
        # for module-level constants is handled by load_env or has defaults.
        # Let's ensure GCS_BUCKET_NAME is set as it's used in FileIngestRequest.clean_file_path
        # and other parts of main.py for constructing GCS paths.
        os.environ['GCS_BUCKET_NAME'] = 'test-bucket'
        os.environ['POSTGRES_URL'] = 'postgresql://user:pass@host:port/db' # For PGVectorStore
        os.environ['DJANGO_API_KEY'] = 'test-django-api-key' # For settings.update_file_progress

    def tearDown(self):
        # Clean up any environment variables set during a test if necessary
        del os.environ['GCS_BUCKET_NAME']
        del os.environ['POSTGRES_URL']
        del os.environ['DJANGO_API_KEY']


    @patch('main.GCSReader')
    @patch('main.VectorStoreIndex')
    @patch('main.PGVectorStore')
    @patch('main.OpenAIEmbedding')
    @patch('main.GeminiEmbedding')
    @patch('main.settings.update_file_progress', new_callable=AsyncMock)
    def test_ingest_file_with_project_id(self, mock_update_progress, mock_gemini_embed,
                                         mock_openai_embed, mock_pg_vector_store_cls,
                                         mock_vector_store_index_cls, mock_gcs_reader_cls):

        mock_gcs_reader_instance = MagicMock()
        initial_doc = LlamaDocument(text="file content from GCS", id_="doc_gcs_1", metadata={'original_key': 'original_value'})
        mock_gcs_reader_instance.load_data.return_value = [initial_doc]
        mock_gcs_reader_cls.return_value = mock_gcs_reader_instance

        # Mock the from_documents class method to capture arguments
        # This is the point where chunked documents with enriched metadata will be passed.
        mock_from_documents_method = MagicMock()
        mock_vector_store_index_cls.from_documents = mock_from_documents_method

        mock_openai_embed.return_value = MagicMock(dimensions=1536) # Ensure dimensions is mockable if accessed
        mock_gemini_embed.return_value = MagicMock(dimensions=768)

        payload = {
            "file_path": "gs://test-bucket/test_file.pdf",
            "vector_table_name": "test_vector_table",
            "file_uuid": "file_uuid_project_test",
            "link_id": 201,
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-ada-002",
            "project_id": "project_uuid_for_ingestion",
            "chunk_size": 500,
            "chunk_overlap": 100,
            "batch_size": 5, # Pydantic model has this
            "progress_update_frequency": 10 # Pydantic model has this
        }
        response = self.client.post("/ingest-file", json=payload)
        self.assertEqual(response.status_code, 200, response.json())

        mock_from_documents_method.assert_called_once()

        args, kwargs = mock_from_documents_method.call_args
        indexed_documents_chunks = args[0]

        self.assertTrue(len(indexed_documents_chunks) > 0, "No document chunks were sent for indexing.")
        for chunk_doc in indexed_documents_chunks:
            self.assertIsInstance(chunk_doc, LlamaDocument)
            self.assertIn('file_uuid', chunk_doc.metadata)
            self.assertEqual(chunk_doc.metadata['file_uuid'], "file_uuid_project_test")
            self.assertIn('link_id', chunk_doc.metadata)
            self.assertEqual(chunk_doc.metadata['link_id'], "201")
            self.assertIn('project_id', chunk_doc.metadata)
            self.assertEqual(chunk_doc.metadata['project_id'], "project_uuid_for_ingestion")
            self.assertIn('original_key', chunk_doc.metadata, "Original metadata should be preserved.")


    @patch('main.GCSReader')
    @patch('main.VectorStoreIndex')
    @patch('main.PGVectorStore')
    @patch('main.OpenAIEmbedding')
    @patch('main.GeminiEmbedding')
    @patch('main.settings.update_file_progress', new_callable=AsyncMock)
    def test_ingest_file_without_project_id(self, mock_update_progress, mock_gemini_embed,
                                           mock_openai_embed, mock_pg_vector_store_cls,
                                           mock_vector_store_index_cls, mock_gcs_reader_cls):
        mock_gcs_reader_instance = MagicMock()
        initial_doc = LlamaDocument(text="another file content", id_="doc_gcs_2") # No initial metadata
        mock_gcs_reader_instance.load_data.return_value = [initial_doc]
        mock_gcs_reader_cls.return_value = mock_gcs_reader_instance

        mock_from_documents_method = MagicMock()
        mock_vector_store_index_cls.from_documents = mock_from_documents_method

        mock_openai_embed.return_value = MagicMock(dimensions=1536)
        mock_gemini_embed.return_value = MagicMock(dimensions=768)

        payload = {
            "file_path": "gs://test-bucket/test_file_no_proj.pdf",
            "vector_table_name": "test_vector_table_no_proj",
            "file_uuid": "file_uuid_no_project_test",
            "link_id": 202,
            "embedding_provider": "google", # Test with google provider
            "embedding_model": "models/embedding-004",
            # project_id is omitted here
            "chunk_size": 600,
            "chunk_overlap": 150,
            "batch_size": 3,
            "progress_update_frequency": 5
        }
        response = self.client.post("/ingest-file", json=payload)
        self.assertEqual(response.status_code, 200, response.json())

        mock_from_documents_method.assert_called_once()
        args, kwargs = mock_from_documents_method.call_args
        indexed_documents_chunks = args[0]

        self.assertTrue(len(indexed_documents_chunks) > 0, "No document chunks were sent for indexing.")
        for chunk_doc in indexed_documents_chunks:
            self.assertIsInstance(chunk_doc, LlamaDocument)
            self.assertIn('file_uuid', chunk_doc.metadata)
            self.assertEqual(chunk_doc.metadata['file_uuid'], "file_uuid_no_project_test")
            self.assertIn('link_id', chunk_doc.metadata)
            self.assertEqual(chunk_doc.metadata['link_id'], "202")
            self.assertNotIn('project_id', chunk_doc.metadata, "project_id should not be in metadata when not provided.")

    def test_ingest_file_missing_required_field_fastapi(self):
        # Test FastAPI's handling of Pydantic model validation
        payload = {
            "file_path": "gs://test-bucket/test_file_missing_field.pdf",
            # "file_uuid": "file_uuid_missing", # file_uuid is required by FileIngestRequest
            "link_id": 203,
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-ada-002",
            "vector_table_name": "test_vector_table_missing",
            "chunk_size": 500,
            "chunk_overlap": 100,
            "batch_size": 5,
            "progress_update_frequency": 10
        }
        response = self.client.post("/ingest-file", json=payload)
        self.assertEqual(response.status_code, 422) # FastAPI's Unprocessable Entity
        self.assertIn("file_uuid", response.json()["detail"][0]["loc"])


# This allows running the tests directly if this file is executed
if __name__ == '__main__':
    # Stop the patcher for load_env if it was started globally for the module
    # This is important if tests are run multiple times in a session or with a test runner
    # that might not re-import modules cleanly.
    if patcher_load_env.is_started:
         patcher_load_env.stop()
    unittest.main()

```
