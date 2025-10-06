# Comprehensive Audit Implementation Design

## Overview

This document outlines the design and implementation requirements for comprehensive auditing in the Reggie SaaS application to meet legal industry compliance standards. The audit system must provide forensic-level accountability for all user actions and data modifications.

## Current State Analysis

### Existing Audit Capabilities

#### ✅ Basic Infrastructure
- **Django/DRF Architecture**: Solid foundation with proper authentication
- **Basic Logging**: Console-based logging configured for production
- **User Management**: Custom user model with proper authentication
- **API Structure**: Well-organized ViewSets for all major entities
- **Error Handling**: Some error logging in place (admin actions, tasks)

#### ❌ Critical Gaps
- **No Model-Level Auditing**: No audit trails for data changes
- **Missing Security Event Logging**: Basic authentication logging only
- **No Legal-Specific Audit Models**: No legal industry features
- **Inadequate Logging Configuration**: Basic console logging only

## Audit Library Architecture

### Three-Library Approach

#### 1. django-auditlog - Core Data Integrity
**Role**: Primary audit trail for all model changes
**Why**: 
- ✅ **Performance optimized** for high-volume legal data
- ✅ **Immutable audit logs** (critical for legal discovery)
- ✅ **Simple integration** with existing models
- ✅ **Built-in serialization** of model changes

#### 2. django-simple-history - Version Control & Rollback
**Role**: Document versioning and legal document history
**Why**:
- ✅ **Perfect for legal documents** (version control is crucial)
- ✅ **Easy rollback** to previous versions
- ✅ **Historical queries** for legal research
- ✅ **Lightweight** and doesn't impact performance

#### 3. django-easy-audit - User Behavior & Security
**Role**: Comprehensive user activity tracking
**Why**:
- ✅ **Tracks user behavior** (logins, requests, permissions)
- ✅ **Security-focused** (perfect for legal compliance)
- ✅ **Request-level logging** (API calls, page views)
- ✅ **User session tracking**

## Data Models

### Core Audit Models

```python
# apps/audit/models.py
from django.db import models
from apps.utils.models import BaseModel
from apps.users.models import CustomUser

class AuditLog(BaseModel):
    """Central audit log for all system events"""
    
    # Event identification
    event_type = models.CharField(max_length=50)  # create, update, delete, login, etc.
    resource_type = models.CharField(max_length=100)  # Agent, Document, File, etc.
    resource_id = models.CharField(max_length=255)  # ID of the affected resource
    
    # User context
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    session_id = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    
    # Event details
    action_description = models.TextField()
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    
    # Legal context
    case_id = models.CharField(max_length=100, blank=True)
    client_id = models.CharField(max_length=100, blank=True)
    
    # Security context
    is_security_event = models.BooleanField(default=False)
    risk_level = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], default='low')
    
    # Validation
    requires_review = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(CustomUser, related_name='reviewed_audits', null=True, blank=True)
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['case_id', 'created_at']),
            models.Index(fields=['is_security_event', 'created_at']),
        ]

class SecurityEvent(BaseModel):
    """Dedicated model for security-related events"""
    
    event_type = models.CharField(max_length=50, choices=[
        ('login_success', 'Successful Login'),
        ('login_failed', 'Failed Login'),
        ('logout', 'Logout'),
        ('permission_change', 'Permission Change'),
        ('api_key_created', 'API Key Created'),
        ('api_key_revoked', 'API Key Revoked'),
        ('unauthorized_access', 'Unauthorized Access'),
        ('data_export', 'Data Export'),
        ('data_import', 'Data Import'),
        ('configuration_change', 'Configuration Change'),
    ])
    
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    session_id = models.CharField(max_length=255, blank=True)
    
    # Event details
    description = models.TextField()
    affected_resource = models.CharField(max_length=255, blank=True)
    risk_level = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ])
    
    # Investigation
    requires_investigation = models.BooleanField(default=False)
    investigation_notes = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(CustomUser, related_name='resolved_security_events', null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['risk_level', 'created_at']),
            models.Index(fields=['requires_investigation', 'created_at']),
        ]
```

### Legal-Specific Audit Models

```python
class LegalAuditTrail(BaseModel):
    """Audit trail specifically for legal industry compliance"""
    
    # Legal context
    case_id = models.CharField(max_length=100)
    client_id = models.CharField(max_length=100)
    matter_type = models.CharField(max_length=100)  # litigation, corporate, etc.
    jurisdiction = models.CharField(max_length=100)
    
    # Citation tracking
    citation_id = models.UUIDField(null=True, blank=True)
    source_documents = models.JSONField(default=list)
    ai_model_used = models.CharField(max_length=100, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    
    # Legal review
    requires_legal_review = models.BooleanField(default=True)
    legal_reviewer = models.ForeignKey(CustomUser, null=True, blank=True)
    review_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision')
    ], default='pending')
    
    # Privilege protection
    is_privileged = models.BooleanField(default=False)
    privilege_level = models.CharField(max_length=50, choices=[
        ('attorney_client', 'Attorney-Client'),
        ('work_product', 'Work Product'),
        ('confidential', 'Confidential'),
        ('public', 'Public')
    ], default='confidential')
    
    # Audit details
    event_type = models.CharField(max_length=50)
    description = models.TextField()
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['case_id', 'created_at']),
            models.Index(fields=['client_id', 'created_at']),
            models.Index(fields=['privilege_level', 'created_at']),
            models.Index(fields=['review_status', 'created_at']),
        ]
```

## Implementation Strategy

### Phase 1: Core Audit Infrastructure (Week 1)

#### 1.1 Install Audit Libraries
```bash
pip install django-auditlog django-simple-history django-easy-audit
```

#### 1.2 Configure django-auditlog
```python
# settings.py
INSTALLED_APPS = [
    'auditlog',
    'simple_history',
    'easyaudit',
    # ... other apps
]

# apps/opie/models.py
from auditlog.registry import auditlog

# Register critical models
auditlog.register(Agent)
auditlog.register(KnowledgeBase)
auditlog.register(File)
auditlog.register(Collection)
auditlog.register(CustomUser)

# apps/docs/models.py
auditlog.register(Document)
```

#### 1.3 Configure django-simple-history
```python
# apps/docs/models.py
from simple_history.models import HistoricalRecords

class Document(MP_Node, BaseModel):
    # ... existing fields
    history = HistoricalRecords()

# apps/opie/models.py
class KnowledgeBase(BaseModel):
    # ... existing fields
    history = HistoricalRecords()
```

#### 1.4 Configure django-easy-audit
```python
# settings.py
EASYAUDIT_READONLY_EVENTS = True
EASYAUDIT_READONLY_FIELDS = True
EASYAUDIT_CRUD_DIFFERENCE_CALLBACKS = []
```

### Phase 2: Security Event Logging (Week 2)

#### 2.1 Custom Security Logger
```python
# apps/audit/security_logger.py
import logging
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from .models import SecurityEvent

security_logger = logging.getLogger('security')

@receiver(user_logged_in)
def log_user_login(sender, user, request, **kwargs):
    SecurityEvent.objects.create(
        event_type='login_success',
        user=user,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        session_id=request.session.session_key,
        description=f'User {user.email} logged in successfully',
        risk_level='low'
    )

@receiver(user_logged_out)
def log_user_logout(sender, user, request, **kwargs):
    SecurityEvent.objects.create(
        event_type='logout',
        user=user,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        session_id=request.session.session_key,
        description=f'User {user.email} logged out',
        risk_level='low'
    )

def log_permission_change(user, target_user, permission, action):
    SecurityEvent.objects.create(
        event_type='permission_change',
        user=user,
        ip_address='127.0.0.1',  # Get from request context
        user_agent='',
        description=f'User {user.email} {action} {permission} for {target_user.email}',
        affected_resource=f'User:{target_user.id}',
        risk_level='high',
        requires_investigation=True
    )
```

#### 2.2 API Key Management Auditing
```python
# apps/api/models.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import UserAPIKey
from apps.audit.security_logger import log_api_key_action

@receiver(post_save, sender=UserAPIKey)
def log_api_key_created(sender, instance, created, **kwargs):
    if created:
        log_api_key_action('created', instance)

@receiver(post_delete, sender=UserAPIKey)
def log_api_key_deleted(sender, instance, **kwargs):
    log_api_key_action('deleted', instance)
```

### Phase 3: Legal-Specific Features (Week 3)

#### 3.1 Legal Audit Middleware
```python
# apps/audit/middleware.py
from django.utils.deprecation import MiddlewareMixin
from .models import LegalAuditTrail

class LegalAuditMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Extract legal context from request
        case_id = request.headers.get('X-Case-ID', '')
        client_id = request.headers.get('X-Client-ID', '')
        
        # Store in request for use in views
        request.legal_context = {
            'case_id': case_id,
            'client_id': client_id,
        }
    
    def process_response(self, request, response):
        # Log legal-specific events
        if hasattr(request, 'legal_context') and request.legal_context.get('case_id'):
            self.log_legal_event(request, response)
        return response
    
    def log_legal_event(self, request, response):
        # Log legal events with case context
        pass
```

#### 3.2 Citation Provenance Integration
```python
# apps/audit/citation_tracker.py
from .models import LegalAuditTrail
from apps.legal.models import LegalCitationProvenance

def track_citation_generation(citation_provenance, request):
    """Track citation generation in legal audit trail"""
    LegalAuditTrail.objects.create(
        case_id=request.legal_context.get('case_id', ''),
        client_id=request.legal_context.get('client_id', ''),
        citation_id=citation_provenance.citation_id,
        source_documents=citation_provenance.source_documents,
        ai_model_used=citation_provenance.ai_model,
        confidence_score=citation_provenance.confidence_score,
        event_type='citation_generated',
        description=f'AI generated citation with {len(citation_provenance.source_documents)} sources',
        is_privileged=True,
        privilege_level='attorney_client'
    )
```

### Phase 4: Enhanced Logging Configuration (Week 4)

#### 4.1 Structured Logging
```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s", "user": "%(user)s", "ip": "%(ip)s", "case_id": "%(case_id)s"}',
        },
        'security': {
            'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "event_type": "%(event_type)s", "user": "%(user)s", "ip": "%(ip)s", "risk_level": "%(risk_level)s", "message": "%(message)s"}',
        },
    },
    'handlers': {
        'security_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/security.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'security',
        },
        'audit_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/audit.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'json',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'loggers': {
        'security': {
            'handlers': ['security_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'audit': {
            'handlers': ['audit_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.audit': {
            'handlers': ['audit_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
```

#### 4.2 Centralized Log Management
```python
# apps/audit/log_management.py
import logging
from django.conf import settings
from .models import AuditLog, SecurityEvent

class AuditLogManager:
    """Centralized audit log management"""
    
    def __init__(self):
        self.audit_logger = logging.getLogger('audit')
        self.security_logger = logging.getLogger('security')
    
    def log_model_change(self, instance, action, user, request=None):
        """Log model changes with full context"""
        context = self._get_request_context(request)
        
        self.audit_logger.info(
            f"Model {action}",
            extra={
                'user': user.email if user else 'system',
                'ip': context.get('ip_address'),
                'case_id': context.get('case_id'),
                'resource_type': instance.__class__.__name__,
                'resource_id': str(instance.pk),
                'action': action,
            }
        )
        
        # Store in database
        AuditLog.objects.create(
            event_type=action,
            resource_type=instance.__class__.__name__,
            resource_id=str(instance.pk),
            user=user,
            ip_address=context.get('ip_address'),
            user_agent=context.get('user_agent'),
            session_id=context.get('session_id'),
            action_description=f"{action} {instance.__class__.__name__} {instance.pk}",
            case_id=context.get('case_id'),
            client_id=context.get('client_id'),
        )
    
    def log_security_event(self, event_type, user, request, description, risk_level='low'):
        """Log security events with appropriate risk assessment"""
        context = self._get_request_context(request)
        
        self.security_logger.warning(
            f"Security event: {event_type}",
            extra={
                'event_type': event_type,
                'user': user.email if user else 'anonymous',
                'ip': context.get('ip_address'),
                'risk_level': risk_level,
                'message': description,
            }
        )
        
        # Store in database
        SecurityEvent.objects.create(
            event_type=event_type,
            user=user,
            ip_address=context.get('ip_address'),
            user_agent=context.get('user_agent'),
            session_id=context.get('session_id'),
            description=description,
            risk_level=risk_level,
            requires_investigation=risk_level in ['high', 'critical']
        )
    
    def _get_request_context(self, request):
        """Extract context from request"""
        if not request:
            return {}
        
        return {
            'ip_address': self._get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'session_id': request.session.session_key,
            'case_id': getattr(request, 'legal_context', {}).get('case_id', ''),
            'client_id': getattr(request, 'legal_context', {}).get('client_id', ''),
        }
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
```

## API Endpoints

### Audit Log Management
```python
# apps/audit/views.py
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from .models import AuditLog, SecurityEvent, LegalAuditTrail
from .serializers import AuditLogSerializer, SecurityEventSerializer, LegalAuditTrailSerializer

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for audit logs"""
    serializer_class = AuditLogSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event_type', 'resource_type', 'user', 'case_id', 'is_security_event']
    search_fields = ['action_description', 'resource_id']
    ordering_fields = ['created_at', 'event_type']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return AuditLog.objects.all()

class SecurityEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for security events"""
    serializer_class = SecurityEventSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event_type', 'user', 'risk_level', 'requires_investigation', 'resolved']
    search_fields = ['description', 'affected_resource']
    ordering_fields = ['created_at', 'risk_level']
    ordering = ['-created_at']
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark security event as resolved"""
        event = self.get_object()
        event.resolved = True
        event.resolved_by = request.user
        event.resolved_at = timezone.now()
        event.investigation_notes = request.data.get('notes', '')
        event.save()
        return Response({'status': 'resolved'})

class LegalAuditTrailViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for legal audit trails"""
    serializer_class = LegalAuditTrailSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['case_id', 'client_id', 'matter_type', 'jurisdiction', 'privilege_level', 'review_status']
    search_fields = ['description', 'citation_id']
    ordering_fields = ['created_at', 'privilege_level']
    ordering = ['-created_at']
    
    def get_queryset(self):
        # Filter by case/client access permissions
        return LegalAuditTrail.objects.all()
```

## Security Considerations

### Data Protection
- **Encryption at rest** for sensitive audit data
- **Access control** based on user roles and case permissions
- **Audit log integrity** with digital signatures
- **Data retention** policies for legal compliance

### Privacy
- **PII masking** in audit logs
- **Client data isolation** between cases
- **Privilege protection** for attorney-client communications
- **Secure deletion** of expired audit data

## Performance Considerations

### Database Optimization
- **Indexing strategy** for audit queries
- **Partitioning** by date for large audit tables
- **Archival** of old audit data
- **Read replicas** for audit queries

### Scalability
- **Async processing** for audit log creation
- **Queue management** for high-volume events
- **Caching** for frequently accessed audit data
- **Monitoring** for audit system performance

## Compliance Requirements

### Legal Industry Standards
- **SOC 2 Type II** certification
- **ISO 27001** compliance
- **State Bar** requirements
- **HIPAA** compliance (if applicable)

### Audit Requirements
- **Complete audit trail** for all actions
- **Immutable audit logs** for legal discovery
- **Human review** for critical events
- **Regular audit** of audit system itself

## Conclusion

This comprehensive audit implementation design provides the foundation for meeting legal industry compliance requirements. The phased approach ensures gradual implementation while maintaining system stability and user experience.

Key success factors:
1. **Complete coverage** of all user actions and data modifications
2. **Legal-specific features** for citation provenance and case tracking
3. **Security event logging** for threat detection and response
4. **Performance optimization** for high-volume audit data
5. **Compliance** with legal industry standards and regulations
