from llama_index.core.node_parser import NodeParser
from llama_index.readers.docling import DoclingReader
from llama_index.node_parser.docling import DoclingNodeParser
from llama_index.core.node_parser import MarkdownNodeParser
from typing import Any, Dict, List
from llama_index.core.schema import Document, BaseNode

class DoclingSplitter(NodeParser):
    """
    A splitter that uses the Docling parser to extract structured information from documents.
    This class is designed to be configurable to support different output formats from Docling,
    such as rich JSON or simpler Markdown.
    """
    def __init__(self, export_type: DoclingReader.ExportType = DoclingReader.ExportType.JSON, **kwargs):
        """
        Initializes the DoclingSplitter.
        Args:
            export_type: The format for Docling to export the document to.
                         Defaults to JSON for rich metadata.
        """
        self.export_type = export_type
        self.reader = DoclingReader(export_type=self.export_type)

        if self.export_type == DoclingReader.ExportType.JSON:
            self.node_parser = DoclingNodeParser(**kwargs)
        elif self.export_type == DoclingReader.ExportType.MD:
            self.node_parser = MarkdownNodeParser(**kwargs)
        else:
            raise ValueError(f"Unsupported export type for DoclingSplitter: {self.export_type}")

        super().__init__(**kwargs)

    def _parse_nodes(self, nodes: List[BaseNode], show_progress: bool = False, **kwargs: Any) -> List[BaseNode]:
        """This method is not used for this splitter as it operates on file paths."""
        raise NotImplementedError("DoclingSplitter operates on file paths, not pre-loaded nodes.")

    def get_nodes_from_documents(self, documents: List[Document], show_progress: bool = False, **kwargs: Any) -> List[BaseNode]:
        """
        Processes a list of documents (which should contain file paths) using the Docling engine.
        Args:
            documents: A list of Document objects. It is expected that each Document's `id_`
                       or a metadata field contains the file path to process.
            show_progress: Whether to display a progress bar.
        Returns:
            A list of parsed BaseNode objects with rich metadata.
        """
        all_nodes = []
        for doc in documents:
            # Assumes the file_path is stored in the document's metadata
            file_path = doc.metadata.get("file_path")
            if not file_path:
                raise ValueError("Document metadata must contain a 'file_path' for DoclingSplitter.")

            # DoclingReader loads the data from the file path
            docling_docs = self.reader.load_data(file_path)

            # The corresponding node parser then creates nodes from the loaded data
            nodes = self.node_parser.get_nodes_from_documents(docling_docs, show_progress=show_progress)
            all_nodes.extend(nodes)

        return all_nodes

    @classmethod
    def from_defaults(cls, **kwargs: Any) -> "DoclingSplitter":
        """Load a DoclingSplitter from defaults."""
        return cls(**kwargs)

    def _get_nodes_from_doc(self, doc: Document, **kwargs) -> List[BaseNode]:
        """This is a helper function for the base class and is not the primary entry point."""
        return self.get_nodes_from_documents([doc], **kwargs)
