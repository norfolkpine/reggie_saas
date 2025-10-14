from llama_index.core.node_parser import TokenTextSplitter, NodeParser
from typing import Any
import re
from strategies.legislation_splitter import LegislationSplitter
from strategies.presentation_splitter import PresentationSplitter
from strategies.qa_splitter import QASplitter

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
        return LegislationSplitter()

    else:
        raise ValueError(f"Unknown chunking strategy: {strategy_id}")
