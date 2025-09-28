# Chunking Strategy Management System

## Overview

The chunking strategy management system provides centralized control over how documents are split into chunks for vector storage and retrieval. This system allows you to define different chunking strategies optimized for different document types and use cases.

## Architecture

### ChunkingStrategy Model

The `ChunkingStrategy` model is the central configuration point for all chunking behavior:

**Core Fields:**
- `name`: Human-readable strategy name
- `description`: When to use this strategy
- `strategy_type`: The chunking algorithm type
- `document_type`: What documents it's optimized for
- `chunk_size` & `chunk_overlap`: Default parameters
- `advanced_parameters`: JSON field for strategy-specific settings
- `is_active`: Whether this strategy is available
- `is_default`: Whether this is the default strategy

### Integration Points

- **KnowledgeBase**: Uses chunking strategy with optional overrides
- **VaultFile**: Uses chunking strategy with optional overrides
- **main.py**: Receives effective chunking settings via API

## Chunking Strategies

### 1. Legal Documents Strategy

**Purpose**: Optimized for legal documents with section awareness

```python
{
    "name": "Legal Documents - Standard",
    "strategy_type": "legal",
    "document_type": "legal", 
    "chunk_size": 300,
    "chunk_overlap": 150,
    "advanced_parameters": {
        "preserve_sections": True,
        "table_as_chunk": True,
        "guide_as_chunk": True,
        "similarity_cutoff": 0.7
    }
}
```

**Behavior:**
- Splits on legal section boundaries (21-1, 21-5, etc.)
- Keeps complete legal sections together
- Tables and guides as single chunks
- Higher similarity cutoff for precision
- Preserves legal document structure

**Use Cases:**
- Tax law documents
- Legal contracts
- Regulatory compliance documents
- Court decisions

### 2. Vault Documents Strategy

**Purpose**: Auto-detects document type and applies appropriate chunking

```python
{
    "name": "Vault Documents - Mixed Content",
    "strategy_type": "vault",
    "document_type": "mixed",
    "chunk_size": 500,
    "chunk_overlap": 100,
    "advanced_parameters": {
        "auto_detect_type": True,
        "fallback_strategy": "token",
        "similarity_cutoff": 0.6
    }
}
```

**Behavior:**
- Auto-detects document type (legal, structured, general)
- Applies different chunking per detected type
- Larger chunks for mixed content
- Lower similarity cutoff for broader retrieval
- Handles diverse document types in vault

**Use Cases:**
- Mixed document vaults
- Project files with various content types
- User-uploaded documents
- General knowledge bases

### 3. Semantic Chunking Strategy

**Purpose**: Uses embedding similarity for precise chunk boundaries

```python
{
    "name": "Semantic Chunking - High Precision",
    "strategy_type": "semantic",
    "document_type": "general",
    "chunk_size": 400,
    "chunk_overlap": 100,
    "advanced_parameters": {
        "buffer_size": 1,
        "breakpoint_percentile_threshold": 95,
        "include_metadata": True,
        "include_prev_next_rel": True
    }
}
```

**Behavior:**
- Uses embedding similarity for chunk boundaries
- Groups semantically related content
- Requires embedding model
- High precision threshold (95%)
- Maintains semantic coherence

**Use Cases:**
- Technical documentation
- Research papers
- Educational content
- Knowledge articles

### 4. Hierarchical Chunking Strategy

**Purpose**: Creates parent-child chunk relationships

```python
{
    "name": "Hierarchical Chunking - Multi-level",
    "strategy_type": "hierarchical",
    "document_type": "general",
    "chunk_size": 600,
    "chunk_overlap": 150,
    "advanced_parameters": {
        "parent_chunk_size": 600,
        "child_chunk_size": 300,
        "include_metadata": True,
        "include_prev_next_rel": True
    }
}
```

**Behavior:**
- Creates parent-child chunk relationships
- Two-level chunking (600/300 tokens)
- Maintains hierarchical context
- Requires embedding model
- Preserves document structure

**Use Cases:**
- Structured documents
- Technical manuals
- API documentation
- Complex reports

### 5. Agentic Chunking Strategy

**Purpose**: AI-powered boundary detection

```python
{
    "name": "Agentic Chunking - AI-Powered",
    "strategy_type": "agentic",
    "document_type": "mixed",
    "chunk_size": 400,
    "chunk_overlap": 120,
    "advanced_parameters": {
        "ai_boundary_detection": True,
        "context_preservation": True,
        "similarity_cutoff": 0.7,
        "smart_overlap": True
    }
}
```

**Behavior:**
- AI-powered boundary detection
- Context-aware splitting
- Smart overlap calculation
- Adapts to document structure
- Uses pattern recognition

**Use Cases:**
- Complex legal documents
- Mixed content types
- Documents with unusual structure
- High-precision requirements

### 6. Token-based Chunking Strategy

**Purpose**: Simple token-based splitting

```python
{
    "name": "Token-based - Simple",
    "strategy_type": "token",
    "document_type": "general",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "advanced_parameters": {
        "separator": "\\n\\n",
        "secondary_chunking_regex": "[.!?]\\s+",
        "chunk_overlap_ratio": 0.2
    }
}
```

**Behavior:**
- Simple token-based splitting
- Fallback option
- No embedding model required
- Paragraph-based splitting
- Reliable and fast

**Use Cases:**
- Simple documents
- Fallback strategy
- High-volume processing
- Basic text files

## Usage Examples

### Creating a Knowledge Base

```python
# Create a legal knowledge base
kb = KnowledgeBase.objects.create(
    name="Tax Law KB",
    chunking_strategy=ChunkingStrategy.objects.get(name="Legal Documents - Standard"),
    chunk_size=400,  # Override: larger chunks for this KB
    chunk_overlap=200  # Override: more overlap for this KB
)

# Effective settings: 400 chunk_size, 200 chunk_overlap (overrides applied)
```

### Creating a Vault File

```python
# Create a vault file with mixed content strategy
vault_file = VaultFile.objects.create(
    original_filename="contract.pdf",
    chunking_strategy=ChunkingStrategy.objects.get(name="Vault Documents - Mixed Content"),
    chunk_size=600,  # Override: larger chunks for this file
    chunk_overlap=150  # Override: more overlap for this file
)

# Effective settings: 600 chunk_size, 150 chunk_overlap (overrides applied)
```

### API Usage

```python
# Get effective chunking settings
if vault_file.chunking_strategy:
    effective_chunk_size = vault_file.chunking_strategy.get_effective_chunk_size(vault_file.chunk_size)
    effective_chunk_overlap = vault_file.chunking_strategy.get_effective_chunk_overlap(vault_file.chunk_overlap)
    chunking_strategy = vault_file.chunking_strategy.strategy_type
    document_type = vault_file.chunking_strategy.document_type
```

## Configuration

### Default Strategies

The system comes with pre-configured strategies:

1. **Legal Documents - Standard**: 300/150 tokens, section-aware
2. **Legal Documents - Large Sections**: 500/200 tokens, for large sections
3. **Vault Documents - Mixed Content**: 500/100 tokens, auto-detect
4. **Vault Documents - Legal Focus**: 400/150 tokens, legal patterns
5. **Semantic Chunking - High Precision**: 400/100 tokens, 95% threshold
6. **Hierarchical Chunking - Multi-level**: 600/150 tokens, parent-child
7. **Token-based - Simple**: 1000/200 tokens, basic splitting
8. **Agentic Chunking - AI-Powered**: 400/120 tokens, AI detection

### Creating Custom Strategies

```python
# Create a custom strategy
strategy = ChunkingStrategy.objects.create(
    name="Custom Legal Strategy",
    description="Optimized for specific legal document type",
    strategy_type="legal",
    document_type="legal",
    chunk_size=350,
    chunk_overlap=175,
    advanced_parameters={
        "preserve_sections": True,
        "table_as_chunk": True,
        "similarity_cutoff": 0.8,
        "custom_patterns": ["Section \\d+", "Article \\d+"]
    }
)
```

## Migration and Setup

### 1. Create Migration

```bash
python manage.py makemigrations reggie
```

### 2. Run Migration

```bash
python manage.py migrate
```

### 3. Create Default Strategies

```bash
python manage.py create_default_chunking_strategies
```

## Benefits

### 1. Centralized Management
- All strategies in one place
- Easy to modify and test
- Version control for strategy changes

### 2. Flexible Configuration
- Override any parameter per KB/file
- Strategy reuse across multiple KBs/files
- Fine-tuning without code changes

### 3. Advanced Parameters
- JSON field for strategy-specific settings
- Extensible configuration system
- Custom parameters per strategy type

### 4. Easy Testing
- Create new strategies without code changes
- A/B testing different approaches
- Performance comparison

### 5. Document Type Awareness
- Optimized chunking per content type
- Auto-detection capabilities
- Context-preserving strategies

## Best Practices

### 1. Choose the Right Strategy
- **Legal documents**: Use legal strategies
- **Mixed content**: Use vault strategies
- **Technical docs**: Use semantic strategies
- **Structured docs**: Use hierarchical strategies

### 2. Optimize Parameters
- Start with default settings
- Test with sample documents
- Adjust based on retrieval quality
- Monitor token usage

### 3. Override When Needed
- Use KB/file overrides for specific needs
- Don't create new strategies for minor changes
- Document override reasons

### 4. Monitor Performance
- Track chunk quality metrics
- Monitor token usage
- Measure retrieval accuracy
- Adjust strategies based on results

## Troubleshooting

### Common Issues

1. **High Token Usage**: Reduce chunk size or increase similarity cutoff
2. **Poor Retrieval**: Increase chunk overlap or adjust similarity threshold
3. **Context Loss**: Use legal or hierarchical strategies
4. **Slow Processing**: Use token-based strategy for simple documents

### Debugging

1. Check effective settings in API responses
2. Verify strategy configuration
3. Test with sample documents
4. Monitor ingestion logs

## API Reference

### ChunkingStrategy Model

```python
class ChunkingStrategy(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    strategy_type = models.CharField(max_length=20, choices=STRATEGY_TYPES)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    chunk_size = models.IntegerField()
    chunk_overlap = models.IntegerField()
    advanced_parameters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
```

### Methods

```python
# Get effective chunk size with override
effective_size = strategy.get_effective_chunk_size(override_size)

# Get effective chunk overlap with override
effective_overlap = strategy.get_effective_chunk_overlap(override_overlap)

# Get advanced parameter
value = strategy.get_advanced_parameter('similarity_cutoff', 0.7)

# Set advanced parameter
strategy.set_advanced_parameter('similarity_cutoff', 0.8)
```

This chunking strategy management system provides complete control over document chunking with the flexibility to optimize for different document types and use cases.
