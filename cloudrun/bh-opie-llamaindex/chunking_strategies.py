from llama_index.core.node_parser import TokenTextSplitter, NodeParser
from typing import Any
import re

def get_text_splitter(strategy_id: str, strategy_config: dict[str, Any] | None = None) -> NodeParser:
    """
    Returns a text splitter instance based on the specified strategy.

    Args:
        strategy_id: The identifier for the chunking strategy.
        strategy_config: A dictionary of configuration parameters for the strategy.

    Returns:
        An instance of a LlamaIndex NodeParser.
    """
    strategy_config = strategy_config or {}

    if strategy_id == "default":
        # Default strategy: Token-based splitting.
        chunk_size = strategy_config.get("chunk_size", 1000)
        chunk_overlap = strategy_config.get("chunk_overlap", 200)
        return TokenTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    elif strategy_id == "presentation":
        # Assumes that the document loader provides one document per slide.
        # This splitter therefore treats the entire text of each document as a single chunk.
        return PresentationSplitter()

    elif strategy_id == "qa":
        # Splits text into chunks based on Question/Answer pairs.
        return QASplitter()

    # === Future strategies to be implemented ===

    elif strategy_id == "paper":
        # Section-based chunking for academic papers.
        # This requires a more advanced layout-aware parser.
        return PaperSplitter()

    else:
        raise ValueError(f"Unknown chunking strategy: {strategy_id}")

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

class QASplitter:
    """
    Splits text based on a Question/Answer format. Each Q&A pair becomes a chunk.
    """
    def split_text(self, text: str) -> list[str]:
        """
        Uses regex to find questions (e.g., starting with "Q:") and splits the
        text so that each chunk contains one question and its corresponding answer.
        """

        # Regex to find question prefixes at the beginning of a line.
        q_pattern = re.compile(r"^\s*(Q:|Question:|\d+\.\s*Q\.)", re.IGNORECASE | re.MULTILINE)

        matches = list(q_pattern.finditer(text))

        if not matches:
            return [text.strip()] if text and text.strip() else []

        chunks = []
        for i in range(len(matches)):
            start_pos = matches[i].start()
            # The end of the chunk is the start of the next question, or the end of the text.
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(text)
            chunk = text[start_pos:end_pos].strip()
            if chunk:
                chunks.append(chunk)

        return chunks if chunks else [text.strip()]

class PaperSplitter:
    """
    Section-based splitter for academic papers.
    Extracts metadata (title, abstract, authors, keywords) and chunks by sections.
    """

    def _extract_metadata(self, text: str) -> dict[str, str]:
        """Extract paper metadata like title, abstract, authors, and keywords."""
        metadata = {}

        # Extract title (usually at the beginning, before abstract)
        title_match = re.search(r'^(.+?)(?=\n\s*(?:abstract|authors?|by)\s*:?\s*\n)',
                               text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if title_match:
            metadata['title'] = ' '.join(title_match.group(1).strip().split())

        # Extract abstract
        abstract_match = re.search(r'abstract\s*:?\s*\n(.+?)(?=\n\s*(?:keywords?|key\s*words?|introduction|1\.?\s*introduction)\s*:?\s*\n)',
                                  text, re.IGNORECASE | re.DOTALL)
        if abstract_match:
            metadata['abstract'] = abstract_match.group(1).strip()

        # Extract authors
        authors_match = re.search(r'(?:authors?|by)\s*:?\s*\n(.+?)(?=\n\s*(?:abstract|keywords?)\s*:?\s*\n)',
                                 text, re.IGNORECASE | re.DOTALL)
        if authors_match:
            metadata['authors'] = ' '.join(authors_match.group(1).strip().split())

        # Extract keywords
        keywords_match = re.search(r'(?:keywords?|key\s*words?)\s*:?\s*\n(.+?)(?=\n\s*(?:introduction|1\.?\s*introduction|\d+\.?\s*[A-Z])\s*)',
                                  text, re.IGNORECASE | re.DOTALL)
        if keywords_match:
            metadata['keywords'] = keywords_match.group(1).strip()

        return metadata

    def _find_sections(self, text: str) -> list[tuple[str, str]]:
        """Find section boundaries in the paper text."""
        # Pattern for common section headers (numbered or unnumbered)
        section_pattern = re.compile(
            r'^\s*(?:'
            r'(?:\d+\.?\d*|\d+\.\d+)\s+([A-Z][^\n]{0,100})|'  # Numbered sections: "1. Introduction", "2.1 Methods"
            r'([A-Z][A-Z\s]{2,50})'  # ALL CAPS sections: "INTRODUCTION", "METHODS"
            r')\s*$',
            re.MULTILINE
        )

        matches = list(section_pattern.finditer(text))

        if not matches:
            return [("Content", text.strip())]

        sections = []
        for i in range(len(matches)):
            # Get section title
            section_title = (matches[i].group(1) or matches[i].group(2)).strip()

            # Get section content (from current match to next match or end)
            start_pos = matches[i].end()
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(text)

            section_content = text[start_pos:end_pos].strip()

            if section_content:
                sections.append((section_title, section_content))

        return sections

    def split_text(self, text: str) -> list[str]:
        """
        Splits academic paper text into chunks by sections.
        First chunk contains metadata (title, abstract, authors, keywords).
        Subsequent chunks are individual sections.
        """
        if not text or not text.strip():
            return []

        chunks = []

        # Extract and format metadata
        metadata = self._extract_metadata(text)
        if metadata:
            metadata_text = []
            if 'title' in metadata:
                metadata_text.append(f"Title: {metadata['title']}")
            if 'authors' in metadata:
                metadata_text.append(f"Authors: {metadata['authors']}")
            if 'abstract' in metadata:
                metadata_text.append(f"Abstract: {metadata['abstract']}")
            if 'keywords' in metadata:
                metadata_text.append(f"Keywords: {metadata['keywords']}")

            if metadata_text:
                chunks.append('\n\n'.join(metadata_text))

        # Find and chunk by sections
        sections = self._find_sections(text)

        for section_title, section_content in sections:
            chunk = f"Section: {section_title}\n\n{section_content}"
            chunks.append(chunk)

        return chunks if chunks else [text.strip()]

    def _parse_nodes(self, documents: list, **kwargs) -> list:
        """Passthrough for compatibility with NodeParser interface if needed."""
        return documents