import os
import fitz
from strategies.factory import get_text_splitter
from llama_index.core import Document
from parser.pdf_parser import parse_pdf
import json
import unittest

class TestChunkingStrategies(unittest.TestCase):

    def setUp(self):
        """Set up for the tests."""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.pdf_path = os.path.join(self.base_dir, "test_doc.pdf")

        # Ensure the test PDF exists
        if not os.path.exists(self.pdf_path):
            self.fail(f"Test PDF not found at {self.pdf_path}")

    def test_paper_strategy(self):
        """Test the 'paper' chunking strategy."""
        payload = {"strategy_id": "paper", "strategy_config": {}}
        text_splitter = get_text_splitter(payload["strategy_id"], payload["strategy_config"])

        documents = parse_pdf(self.pdf_path)
        self.assertTrue(len(documents) > 0, "PDF parsing should yield at least one document.")

        all_chunks = []
        for doc in documents:
            text_chunks = text_splitter.split_text(doc.text)
            all_chunks.extend([Document(text=json.dumps(chunk)) for chunk in text_chunks if chunk])

        self.assertTrue(len(all_chunks) > 0, "Paper strategy should produce chunks.")
        print(f"\n--- Paper Strategy produced {len(all_chunks)} chunks ---")

    def test_docling_json_strategy(self):
        """Test the 'docling_json' chunking strategy."""
        payload = {"strategy_id": "docling_json", "strategy_config": {}}
        text_splitter = get_text_splitter(payload["strategy_id"], payload["strategy_config"])

        # Docling operates on a file path, so we create a document pointing to it.
        doc_with_path = Document(metadata={"file_path": self.pdf_path})

        nodes = text_splitter.get_nodes_from_documents([doc_with_path])

        self.assertTrue(len(nodes) > 0, "Docling JSON strategy should produce nodes.")
        self.assertIn("bbox", str(nodes[0].metadata), "JSON nodes should have bounding box metadata.")
        print(f"\n--- Docling JSON Strategy produced {len(nodes)} nodes ---")

    def test_docling_markdown_strategy(self):
        """Test the 'docling_markdown' chunking strategy."""
        payload = {"strategy_id": "docling_markdown", "strategy_config": {}}
        text_splitter = get_text_splitter(payload["strategy_id"], payload["strategy_config"])

        # Docling operates on a file path
        doc_with_path = Document(metadata={"file_path": self.pdf_path})

        nodes = text_splitter.get_nodes_from_documents([doc_with_path])

        self.assertTrue(len(nodes) > 0, "Docling Markdown strategy should produce nodes.")
        # We expect markdown formatting, like '###' for headers
        self.assertTrue(any("###" in node.text for node in nodes), "Markdown nodes should contain markdown formatting.")
        print(f"\n--- Docling Markdown Strategy produced {len(nodes)} nodes ---")


if __name__ == "__main__":
    unittest.main()
