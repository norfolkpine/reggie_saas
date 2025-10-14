"""
Chunking strategies module for LlamaIndex ingestion service.

This module provides a factory function to create text splitters based on
strategy identifiers sent from Django.
"""

from .factory import get_text_splitter

__all__ = ['get_text_splitter']
