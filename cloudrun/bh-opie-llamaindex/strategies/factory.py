from llama_index.core.node_parser import TokenTextSplitter, NodeParser
from typing import Any, Dict


def get_text_splitter(strategy_id: str, strategy_config: Dict[str, Any] | None = None) -> NodeParser:
    """
    Factory function that returns a text splitter instance based on the specified strategy.
    
    Django sends strategy_id and config, Cloud Run instantiates the appropriate strategy.

    Args:
        strategy_id: The identifier for the chunking strategy.
        strategy_config: A dictionary of configuration parameters for the strategy.

    Returns:
        An instance of a LlamaIndex NodeParser.
    """
    strategy_config = strategy_config or {}

    if strategy_id == "default":
        # Default strategy: Sentence-based splitting with paragraph awareness.
        from llama_index.core.node_parser import SentenceSplitter
        chunk_size = strategy_config.get("chunk_size", 500)
        chunk_overlap = strategy_config.get("chunk_overlap", 100)
        return SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            paragraph_separator="\n\n"  # Split on double newlines for paragraph boundaries
        )

    elif strategy_id == "presentation":
        # Assumes that the document loader provides one document per slide.
        # This splitter therefore treats the entire text of each document as a single chunk.
        from .presentation_splitter import PresentationSplitter
        return PresentationSplitter(strategy_config)

    elif strategy_id == "qa":
        # Splits text into chunks based on Question/Answer pairs.
        from .qa_splitter import QASplitter
        return QASplitter(strategy_config)

    elif strategy_id == "legislation":
        # Section-based chunking for legal documents.
        from .legislation_splitter import LegislationSplitter
        return LegislationSplitter(strategy_config)

    # Legacy mapping for "paper" strategy
    elif strategy_id == "paper":
        # Section-based chunking for academic papers.
        # This requires a more advanced layout-aware parser.
        from .legislation_splitter import LegislationSplitter
        return LegislationSplitter(strategy_config)

    elif strategy_id == "docling_json":
        # Uses the Docling parser with rich JSON export for maximum metadata.
        from .docling_splitter import DoclingSplitter
        from llama_index.readers.docling import DoclingReader
        return DoclingSplitter(export_type=DoclingReader.ExportType.JSON, **strategy_config)

    elif strategy_id == "docling_markdown":
        # Uses the Docling parser with Markdown export for simpler, text-focused output.
        from .docling_splitter import DoclingSplitter
        from llama_index.readers.docling import DoclingReader
        return DoclingSplitter(export_type=DoclingReader.ExportType.MD, **strategy_config)

    else:
        raise ValueError(f"Unknown chunking strategy: {strategy_id}")
