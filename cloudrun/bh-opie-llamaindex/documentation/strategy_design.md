# Chunking Strategies

This directory contains the chunking strategy system for the LlamaIndex ingestion service. The system allows Django to select different text chunking strategies when processing documents.

## Architecture

### Flow
```
Django App → strategy_id + config → Cloud Run → strategies/ → instantiate → execute
```

1. **Django** manages strategy metadata and sends `strategy_id` + `strategy_config` to Cloud Run
2. **Cloud Run** receives the request and calls `get_text_splitter(strategy_id, config)`
3. **Factory** instantiates the appropriate strategy based on the ID
4. **Strategy** processes the text and returns a LlamaIndex NodeParser

## File Structure

```
strategies/
├── README.md                 # This file
├── __init__.py              # Clean exports
├── base.py                  # Common interface for all strategies
├── factory.py               # Strategy instantiation logic
├── legislation_splitter.py  # Legislation-specific chunking
├── presentation_splitter.py # Presentation-specific chunking
└── qa_splitter.py          # Q&A-specific chunking
```

## Adding New Strategies

### 1. Create Strategy File
Create a new file (e.g., `mineru_splitter.py`) that implements the base interface:

```python
from .base import BaseStrategy
from llama_index.core.node_parser import NodeParser

class MineruSplitter(BaseStrategy):
    def create_splitter(self) -> NodeParser:
        # Your implementation here
        pass
```

### 2. Register in Factory
Add the strategy to `factory.py`:

```python
elif strategy_id == "mineru":
    from .mineru_splitter import MineruSplitter
    return MineruSplitter(strategy_config)
```

### 3. Update Django
Add the new strategy to your Django models and UI.

## Strategy Configuration

Each strategy can accept configuration parameters through the `strategy_config` dictionary:

```python
# Example: Default strategy with custom chunk size
strategy_config = {
    "chunk_size": 1500,
    "chunk_overlap": 300
}
```

## Available Strategies

- **`default`** - Token-based text splitting with configurable chunk size/overlap
- **`legislation`** - Specialized for legal documents with section-aware chunking
- **`presentation`** - Treats each slide as a single chunk
- **`qa`** - Splits text based on Question/Answer pairs

## Usage in main.py

```python
from strategies import get_text_splitter

# In your ingestion logic:
text_splitter = get_text_splitter(payload.strategy_id, payload.strategy_config)
```

## Design Principles

- **Stateless**: No registration or state management in Cloud Run
- **Django-controlled**: Strategy selection happens in Django
- **Extensible**: Easy to add new strategies without modifying existing code
- **Clean separation**: Cloud Run only executes, Django manages
