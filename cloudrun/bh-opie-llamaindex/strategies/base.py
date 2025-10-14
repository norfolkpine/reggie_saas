from abc import ABC, abstractmethod
from llama_index.core.node_parser import NodeParser
from typing import Any, Dict


class BaseStrategy(ABC):
    """
    Base class for all chunking strategies.
    
    Each strategy should implement the create_splitter method to return
    a LlamaIndex NodeParser configured for the specific chunking approach.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the strategy with configuration.
        
        Args:
            config: Dictionary containing strategy-specific configuration parameters
        """
        self.config = config or {}
    
    @abstractmethod
    def create_splitter(self) -> NodeParser:
        """
        Create and return a LlamaIndex NodeParser instance.
        
        Returns:
            A configured NodeParser instance for text chunking
        """
        pass
