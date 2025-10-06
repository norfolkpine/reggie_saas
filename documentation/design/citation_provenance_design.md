# Citation Provenance Design for Legal Industry Compliance

## Overview

This document outlines the design and implementation requirements for comprehensive citation provenance tracking in AI-generated legal content. The system must provide forensic-level accountability for law firms using AI-generated citations.

## Current State Analysis

### Existing Citation Capabilities

#### ✅ Basic Citation Infrastructure
- **Citation Generation Instructions**: Vault agents instructed to "cite sources" and use "project name, folder name, file names"
- **Citation Streaming**: System streams citations via `"Citations"` events in WebSocket responses
- **Source Metadata Available**: File metadata includes `title`, `original_filename`, `file_type`, `storage_path`, `uploaded_by`

#### ✅ Knowledge Base Integration
- **LlamaIndex integration** with metadata filtering
- **Vector search** with similarity scoring
- **Document retrieval** with source attribution
- **Multi-metadata filtering** for project/user isolation

### Critical Gaps for Legal Industry

#### ❌ No Citation Provenance Tracking
**Current State**: Citations are generated but not tracked
**Legal Requirement**: Complete audit trail of citation sources

#### ❌ No Source Lineage Tracking
**Current State**: No tracking of document → chunk → citation flow
**Legal Requirement**: Complete chain of custody

#### ❌ No Citation Validation Workflow
**Current State**: AI generates citations without human review
**Legal Requirement**: Human validation for legal citations

#### ❌ No Legal-Specific Citation Metadata
**Current State**: Basic file metadata only
**Legal Requirement**: Legal document metadata

## Data Models

### LegalCitationProvenance Model

```python
class LegalCitationProvenance(models.Model):
    """Tracks complete provenance of AI-generated legal citations"""
    
    # Core identification
    citation_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    agent_response_id = models.UUIDField()  # Link to AI response
    session_id = models.CharField(max_length=255)
    
    # Source tracking
    source_documents = models.JSONField()  # List of source document IDs
    source_chunks = models.JSONField()     # Specific text chunks used
    source_metadata = models.JSONField()   # Document metadata at time of citation
    
    # AI generation details
    ai_model = models.CharField(max_length=100)
    model_version = models.CharField(max_length=50)
    prompt_hash = models.CharField(max_length=64)  # Hash of exact prompt used
    confidence_score = models.FloatField()  # Overall confidence
    
    # Legal context
    case_id = models.CharField(max_length=100, blank=True)
    jurisdiction = models.CharField(max_length=100, blank=True)
    legal_domain = models.CharField(max_length=100, blank=True)  # contract, regulation, etc.
    
    # Validation workflow
    requires_review = models.BooleanField(default=True)
    legal_reviewer = models.ForeignKey(CustomUser, null=True, blank=True)
    review_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision')
    ], default='pending')
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, related_name='created_citations')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['case_id', 'created_at']),
            models.Index(fields=['review_status', 'created_at']),
            models.Index(fields=['legal_domain', 'jurisdiction']),
        ]
```

### LegalDocumentMetadata Model

```python
class LegalDocumentMetadata(models.Model):
    """Enhanced metadata for legal documents"""
    
    file = models.OneToOneField(File, on_delete=models.CASCADE)
    
    # Legal-specific metadata
    document_type = models.CharField(max_length=50, choices=[
        ('contract', 'Contract'),
        ('regulation', 'Regulation'),
        ('case_law', 'Case Law'),
        ('statute', 'Statute'),
        ('guideline', 'Guideline'),
        ('policy', 'Policy')
    ])
    
    jurisdiction = models.CharField(max_length=100)
    authority_level = models.CharField(max_length=50, choices=[
        ('federal', 'Federal'),
        ('state', 'State'),
        ('local', 'Local'),
        ('international', 'International')
    ])
    
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    version = models.CharField(max_length=20, default='1.0')
    
    # Citation format
    legal_citation_format = models.CharField(max_length=100)  # Bluebook, etc.
    page_numbers = models.JSONField(default=list)  # Pages referenced
    section_numbers = models.JSONField(default=list)  # Sections referenced
    
    class Meta:
        verbose_name = "Legal Document Metadata"
        verbose_name_plural = "Legal Document Metadata"
```

## Enhanced Agent Instructions

### Current Instructions
```python
# Current (basic)
instructions.append("Be concise and cite sources.")
```

### Enhanced for Legal Industry
```python
# Enhanced for legal industry
instructions.append("""
When generating citations for legal content:
1. Always cite specific document sources with exact page/section references
2. Include document type, jurisdiction, and authority level
3. Use proper legal citation format (Bluebook style)
4. Indicate confidence level for each citation
5. Flag any citations requiring human legal review
6. Include document version and effective dates
7. Specify which parts of documents were used as sources
""")
```

## Citation Validation Workflow

### CitationValidationWorkflow Class

```python
class CitationValidationWorkflow:
    """Handles validation workflow for legal citations"""
    
    def __init__(self, citation_provenance):
        self.citation = citation_provenance
    
    def requires_legal_review(self):
        """Determine if citation requires legal review"""
        return (
            self.citation.confidence_score < 0.8 or
            self.citation.legal_domain in ['case_law', 'regulation'] or
            self.citation.jurisdiction != 'general'
        )
    
    def validate_citation_accuracy(self):
        """Validate citation against source documents"""
        # Check if cited documents still exist
        # Verify page/section references are valid
        # Confirm document versions are current
        pass
    
    def generate_legal_citation_format(self):
        """Generate properly formatted legal citation"""
        # Bluebook format
        # Include all required legal citation elements
        pass
    
    def notify_legal_reviewer(self):
        """Notify assigned legal reviewer of pending citation"""
        if self.citation.legal_reviewer:
            # Send notification email/Slack message
            pass
```

## Integration Points

### 1. Agent Response Enhancement

Modify streaming consumers to capture citation provenance:

```python
# In apps/opie/consumers.py
async def stream_agent_response(self, agent_id, message, session_id, reasoning=None, files=None):
    # ... existing code ...
    
    # Capture citation provenance
    if hasattr(agent, 'run_response') and hasattr(agent.run_response, 'citations'):
        citation_provenance = LegalCitationProvenance.objects.create(
            agent_response_id=response_id,
            session_id=session_id,
            source_documents=extract_source_documents(agent.run_response),
            source_chunks=extract_source_chunks(agent.run_response),
            ai_model=agent.model.id,
            confidence_score=calculate_confidence(agent.run_response),
            created_by=user
        )
```

### 2. Knowledge Base Enhancement

Enhance LlamaIndex integration to track source metadata:

```python
# In apps/opie/agents/helpers/agent_helpers.py
class LegalCitationLlamaIndexKnowledge(CustomLlamaIndexKnowledge):
    def search(self, query: str, num_documents: int = None) -> list[Document]:
        nodes = self.retriever.retrieve(query)
        
        # Enhanced metadata for legal citations
        for node in nodes:
            node.metadata.update({
                'document_type': self.get_document_type(node),
                'jurisdiction': self.get_jurisdiction(node),
                'page_reference': self.get_page_reference(node),
                'section_reference': self.get_section_reference(node),
                'confidence_score': self.calculate_confidence(node, query)
            })
        
        return [Document(text=node.text, metadata=node.metadata) for node in nodes]
```

## Legal Industry Compliance Requirements

### 1. Bar Association Standards
- **Citation accuracy verification**
- **Source document integrity**
- **Human review requirements**
- **Audit trail completeness**

### 2. Discovery Readiness
- **Complete citation lineage**
- **Source document preservation**
- **Metadata immutability**
- **Version control tracking**

### 3. Client Confidentiality
- **Citation isolation by case**
- **Privilege protection**
- **Access control enforcement**
- **Data retention policies**

## Implementation Phases

### Phase 1: Basic Citation Tracking (Week 1)
- [ ] Add `LegalCitationProvenance` model
- [ ] Enhance agent responses to capture citation data
- [ ] Basic source document tracking
- [ ] Database migrations

### Phase 2: Legal Metadata Enhancement (Week 2)
- [ ] Add `LegalDocumentMetadata` model
- [ ] Enhance file upload to capture legal metadata
- [ ] Jurisdiction and authority level tracking
- [ ] Legal document type classification

### Phase 3: Validation Workflow (Week 3)
- [ ] Implement human review requirements
- [ ] Citation accuracy validation
- [ ] Legal compliance checking
- [ ] Notification system for reviewers

### Phase 4: Advanced Features (Week 4)
- [ ] Legal citation formatting (Bluebook style)
- [ ] Case management integration
- [ ] Advanced audit reporting
- [ ] Performance optimization

## API Endpoints

### Citation Management
- `GET /api/v1/citations/` - List citations with filtering
- `GET /api/v1/citations/{id}/` - Get specific citation details
- `POST /api/v1/citations/{id}/review/` - Submit citation review
- `GET /api/v1/citations/pending-review/` - Get citations pending review

### Legal Document Metadata
- `GET /api/v1/legal-documents/` - List legal documents with metadata
- `POST /api/v1/legal-documents/{id}/metadata/` - Update legal metadata
- `GET /api/v1/legal-documents/{id}/citations/` - Get citations for document

## Security Considerations

### Data Protection
- **Encryption at rest** for sensitive legal data
- **Access control** based on case/client permissions
- **Audit logging** for all citation access
- **Data retention** policies for legal compliance

### Privacy
- **Client data isolation** between cases
- **Privilege protection** for attorney-client communications
- **Secure deletion** of expired data
- **Compliance** with legal data protection requirements

## Performance Considerations

### Database Optimization
- **Indexing strategy** for citation queries
- **Partitioning** by case_id for large datasets
- **Caching** for frequently accessed citations
- **Archival** of old citation data

### Scalability
- **Async processing** for citation validation
- **Queue management** for review workflows
- **Load balancing** for high-volume citation generation
- **Monitoring** for citation processing performance

## Testing Strategy

### Unit Tests
- Citation provenance model validation
- Legal metadata extraction
- Citation validation workflow
- API endpoint functionality

### Integration Tests
- End-to-end citation generation
- Agent response enhancement
- Knowledge base integration
- Review workflow completion

### Legal Compliance Tests
- Citation accuracy verification
- Audit trail completeness
- Data retention compliance
- Access control enforcement

## Monitoring and Alerting

### Key Metrics
- Citation generation rate
- Review completion time
- Citation accuracy score
- Legal reviewer workload

### Alerts
- High citation error rate
- Delayed review completion
- Failed citation validation
- Unauthorized access attempts

## Future Enhancements

### Advanced Features
- **AI-powered citation validation**
- **Automated legal citation formatting**
- **Integration with legal research databases**
- **Real-time citation accuracy scoring**

### Compliance Features
- **Multi-jurisdiction support**
- **International legal standards**
- **Regulatory compliance reporting**
- **Advanced audit capabilities**

## Conclusion

This design provides a comprehensive framework for implementing citation provenance tracking that meets legal industry requirements. The phased implementation approach ensures gradual rollout while maintaining system stability and user experience.

The key success factors are:
1. **Complete audit trail** for all citations
2. **Human validation workflow** for legal accuracy
3. **Legal-specific metadata** for proper citation formatting
4. **Integration** with existing agent and knowledge base systems
5. **Compliance** with legal industry standards and regulations
