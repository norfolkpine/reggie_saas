# apps/docs/tests/commands/test_update_files_content_type_metadata.py

from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from apps.docs.factories import DocumentFactory
from apps.docs.models import Document


@pytest.mark.django_db
@patch("google.cloud.storage.Client")
def test_update_files_content_type_metadata(mock_gcs_client):
    # Ensure a clean slate
    Document.objects.all().delete()

    # Create 2 documents
    doc1 = DocumentFactory()
    doc2 = DocumentFactory()

    # Setup GCS mock
    mock_client = MagicMock()
    mock_gcs_client.return_value = mock_client
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    # Helper to create blobs with no content_type
    def make_blob(name):
        blob = MagicMock()
        blob.name = name
        blob.content_type = None
        return blob

    # Create blobs per doc
    mock_blob1 = make_blob(f"{doc1.id}/attachments/file1.txt")
    mock_blob2 = make_blob(f"{doc1.id}/attachments/file2.jpg")
    mock_blob3 = make_blob(f"{doc2.id}/attachments/file1.txt")
    mock_blob4 = make_blob(f"{doc2.id}/attachments/file2.jpg")

    # list_blobs returns per prefix
    def list_blobs_side_effect(prefix):
        if str(doc1.id) in prefix:
            return [mock_blob1, mock_blob2]
        elif str(doc2.id) in prefix:
            return [mock_blob3, mock_blob4]
        return []

    mock_bucket.list_blobs.side_effect = list_blobs_side_effect

    # Patch MIME detector
    with patch("magic.Magic") as mock_magic_class:
        mock_magic = MagicMock()
        mock_magic.from_buffer.return_value = "text/plain"
        mock_magic_class.return_value = mock_magic

        # Simulate download_as_bytes
        for blob in [mock_blob1, mock_blob2, mock_blob3, mock_blob4]:
            blob.download_as_bytes.return_value = b"dummy-data"

        call_command("update_files_content_type_metadata")

    # Each blob should be patched once
    for blob in [mock_blob1, mock_blob2, mock_blob3, mock_blob4]:
        blob.patch.assert_called_once()
        assert blob.content_type == "text/plain"
