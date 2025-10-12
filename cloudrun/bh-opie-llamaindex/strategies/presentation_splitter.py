from llama_index.core.node_parser import TokenTextSplitter, NodeParser
from typing import Any
import re

class PresentationSplitter:
    """
    A simple splitter that treats each document's text as a single chunk.
    This is designed for presentations, where each slide should be its own chunk.
    """
    def split_text(self, text: str) -> list[str]:
        """Returns the text as a single-element list, preserving the entire slide content."""
        return [text] if text and text.strip() else []

    def _parse_nodes(self, documents: list, **kwargs) -> list:
        """Passthrough for compatibility with NodeParser interface if needed."""
        return documents