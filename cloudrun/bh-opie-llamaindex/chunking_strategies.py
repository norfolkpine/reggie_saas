from llama_index.core.node_parser import TokenTextSplitter, NodeParser
from typing import Any

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
        raise NotImplementedError("The 'paper' chunking strategy is not yet implemented.")

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
        import re

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