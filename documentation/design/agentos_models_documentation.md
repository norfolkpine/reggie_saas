# AgentOS Models Documentation

This document provides comprehensive documentation for the AgentOS-related Django models used in the Reggie SaaS application.

## Overview

The AgentOS models provide database persistence and tracking for the Agno (AgentOS) library integration. These models extend the core Agno functionality with Django-specific features like user management, session tracking, metrics, and error handling.

## Model Architecture

### Core Models

#### 1. AgentOSSession
**Purpose**: Tracks AgentOS-specific sessions and interactions

```python
class AgentOSSession(BaseModel):
    """Tracks AgentOS-specific sessions and interactions"""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agentos_sessions"
    )
    agent_id = models.CharField(max_length=128, help_text="AgentOS agent identifier")
    agent_name = models.CharField(max_length=255, help_text="Human-readable agent name")
    session_id = models.CharField(max_length=128, unique=True, help_text="AgentOS session identifier")
    title = models.CharField(max_length=255, default="AgentOS Chat")
    is_active = models.BooleanField(default=True, help_text="Whether the session is currently active")
    message_count = models.PositiveIntegerField(default=0, help_text="Number of messages in this session")
    total_tokens = models.PositiveIntegerField(default=0, help_text="Total tokens used in this session")
    total_cost = models.DecimalField(max_digits=10, decimal_places=6, default=0.0, help_text="Total cost for this session")
    last_activity = models.DateTimeField(auto_now=True, help_text="Last activity timestamp")
    
    class Meta:
        ordering = ["-last_activity"]
        verbose_name = "AgentOS Session"
        verbose_name_plural = "AgentOS Sessions"
        indexes = [
            models.Index(fields=["user", "agent_id"]),
            models.Index(fields=["session_id"]),
            models.Index(fields=["-last_activity"]),
        ]
    
    def __str__(self):
        return f"{self.agent_name} - {self.title} ({self.user})"
```

**Fields**:
- `user` (ForeignKey): Links to the user who created the session
- `agent_id` (CharField, 128): AgentOS agent identifier
- `agent_name` (CharField, 255): Human-readable agent name
- `session_id` (CharField, 128, unique): AgentOS session identifier
- `title` (CharField, 255): Session title (default: "AgentOS Chat")
- `is_active` (BooleanField): Whether the session is currently active
- `message_count` (PositiveIntegerField): Number of messages in this session
- `total_tokens` (PositiveIntegerField): Total tokens used in this session
- `total_cost` (DecimalField): Total cost for this session
- `last_activity` (DateTimeField): Last activity timestamp (auto-updated)

**Indexes**:
- `user`, `agent_id` - For user-specific agent queries
- `session_id` - For session lookups
- `-last_activity` - For recent sessions ordering

**Relationships**:
- One-to-many with `AgentOSMessage`
- One-to-many with `AgentOSError`

#### 2. AgentOSMessage
**Purpose**: Tracks individual messages in AgentOS sessions

```python
class AgentOSMessage(BaseModel):
    """Tracks individual messages in AgentOS sessions"""
    
    session = models.ForeignKey(
        AgentOSSession,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    message_id = models.CharField(max_length=128, help_text="Unique message identifier")
    role = models.CharField(
        max_length=20,
        choices=[
            ("user", "User"),
            ("assistant", "Assistant"),
            ("system", "System"),
        ],
        help_text="Role of the message sender"
    )
    content = models.TextField(help_text="Message content")
    tokens_used = models.PositiveIntegerField(default=0, help_text="Tokens used for this message")
    cost = models.DecimalField(max_digits=10, decimal_places=6, default=0.0, help_text="Cost for this message")
    response_time_ms = models.PositiveIntegerField(default=0, help_text="Response time in milliseconds")
    model_used = models.CharField(max_length=100, blank=True, help_text="Model used for this message")
    tools_used = models.JSONField(default=list, blank=True, help_text="Tools used in this message")
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional message metadata")
    
    class Meta:
        ordering = ["created_at"]
        verbose_name = "AgentOS Message"
        verbose_name_plural = "AgentOS Messages"
        indexes = [
            models.Index(fields=["session", "role"]),
            models.Index(fields=["message_id"]),
            models.Index(fields=["-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}... ({self.session})"
```

**Fields**:
- `session` (ForeignKey): Links to the parent session
- `message_id` (CharField, 128): Unique message identifier
- `role` (CharField, 20): Message role (user/assistant/system)
- `content` (TextField): Message content
- `tokens_used` (PositiveIntegerField): Tokens used for this message
- `cost` (DecimalField): Cost for this message
- `response_time_ms` (PositiveIntegerField): Response time in milliseconds
- `model_used` (CharField, 100): Model used for this message
- `tools_used` (JSONField): Tools used in this message
- `metadata` (JSONField): Additional message metadata

**Indexes**:
- `session`, `role` - For session message queries
- `message_id` - For message lookups
- `-created_at` - For recent messages ordering

#### 3. AgentOSUsage
**Purpose**: Tracks AgentOS usage metrics and statistics

```python
class AgentOSUsage(BaseModel):
    """Tracks AgentOS usage metrics and statistics"""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agentos_usage"
    )
    agent_id = models.CharField(max_length=128, help_text="Agent identifier")
    date = models.DateField(help_text="Date of usage")
    session_count = models.PositiveIntegerField(default=0, help_text="Number of sessions")
    message_count = models.PositiveIntegerField(default=0, help_text="Number of messages")
    total_tokens = models.PositiveIntegerField(default=0, help_text="Total tokens used")
    total_cost = models.DecimalField(max_digits=10, decimal_places=6, default=0.0, help_text="Total cost")
    avg_response_time_ms = models.PositiveIntegerField(default=0, help_text="Average response time")
    unique_tools_used = models.PositiveIntegerField(default=0, help_text="Number of unique tools used")
    
    class Meta:
        ordering = ["-date"]
        verbose_name = "AgentOS Usage"
        verbose_name_plural = "AgentOS Usage"
        unique_together = ["user", "agent_id", "date"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["agent_id", "date"]),
            models.Index(fields=["-date"]),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.agent_id} - {self.date} ({self.total_tokens} tokens)"
```

**Fields**:
- `user` (ForeignKey): Links to the user
- `agent_id` (CharField, 128): Agent identifier
- `date` (DateField): Date of usage
- `session_count` (PositiveIntegerField): Number of sessions
- `message_count` (PositiveIntegerField): Number of messages
- `total_tokens` (PositiveIntegerField): Total tokens used
- `total_cost` (DecimalField): Total cost
- `avg_response_time_ms` (PositiveIntegerField): Average response time
- `unique_tools_used` (PositiveIntegerField): Number of unique tools used

**Constraints**:
- `unique_together`: `user`, `agent_id`, `date` - One record per user/agent/date

**Indexes**:
- `user`, `date` - For user usage queries
- `agent_id`, `date` - For agent usage queries
- `-date` - For recent usage ordering

#### 4. AgentOSPerformance
**Purpose**: Tracks AgentOS performance metrics

```python
class AgentOSPerformance(BaseModel):
    """Tracks AgentOS performance metrics"""
    
    agent_id = models.CharField(max_length=128, help_text="Agent identifier")
    date = models.DateField(help_text="Date of performance measurement")
    total_sessions = models.PositiveIntegerField(default=0, help_text="Total sessions")
    successful_sessions = models.PositiveIntegerField(default=0, help_text="Successful sessions")
    failed_sessions = models.PositiveIntegerField(default=0, help_text="Failed sessions")
    avg_response_time_ms = models.PositiveIntegerField(default=0, help_text="Average response time")
    avg_tokens_per_session = models.PositiveIntegerField(default=0, help_text="Average tokens per session")
    avg_cost_per_session = models.DecimalField(max_digits=10, decimal_places=6, default=0.0, help_text="Average cost per session")
    user_satisfaction_score = models.FloatField(default=0.0, help_text="Average user satisfaction score (0-5)")
    error_rate = models.FloatField(default=0.0, help_text="Error rate percentage")
    
    class Meta:
        ordering = ["-date"]
        verbose_name = "AgentOS Performance"
        verbose_name_plural = "AgentOS Performance"
        unique_together = ["agent_id", "date"]
        indexes = [
            models.Index(fields=["agent_id", "date"]),
            models.Index(fields=["-date"]),
        ]
    
    def __str__(self):
        return f"{self.agent_id} - {self.date} ({self.successful_sessions}/{self.total_sessions})"
    
    @property
    def success_rate(self):
        """Calculate success rate percentage"""
        if self.total_sessions == 0:
            return 0.0
        return (self.successful_sessions / self.total_sessions) * 100
```

**Fields**:
- `agent_id` (CharField, 128): Agent identifier
- `date` (DateField): Date of performance measurement
- `total_sessions` (PositiveIntegerField): Total sessions
- `successful_sessions` (PositiveIntegerField): Successful sessions
- `failed_sessions` (PositiveIntegerField): Failed sessions
- `avg_response_time_ms` (PositiveIntegerField): Average response time
- `avg_tokens_per_session` (PositiveIntegerField): Average tokens per session
- `avg_cost_per_session` (DecimalField): Average cost per session
- `user_satisfaction_score` (FloatField): Average user satisfaction score (0-5)
- `error_rate` (FloatField): Error rate percentage

**Constraints**:
- `unique_together`: `agent_id`, `date` - One record per agent/date

**Properties**:
- `success_rate`: Calculated success rate percentage

#### 5. AgentOSError
**Purpose**: Tracks AgentOS errors and issues

```python
class AgentOSError(BaseModel):
    """Tracks AgentOS errors and issues"""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agentos_errors"
    )
    session = models.ForeignKey(
        AgentOSSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="errors"
    )
    agent_id = models.CharField(max_length=128, help_text="Agent identifier")
    error_type = models.CharField(max_length=100, help_text="Type of error")
    error_message = models.TextField(help_text="Error message")
    error_code = models.CharField(max_length=50, blank=True, help_text="Error code if available")
    stack_trace = models.TextField(blank=True, help_text="Stack trace if available")
    context = models.JSONField(default=dict, blank=True, help_text="Error context and metadata")
    is_resolved = models.BooleanField(default=False, help_text="Whether the error has been resolved")
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="When the error was resolved")
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AgentOS Error"
        verbose_name_plural = "AgentOS Errors"
        indexes = [
            models.Index(fields=["agent_id", "error_type"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_resolved"]),
        ]
    
    def __str__(self):
        return f"{self.error_type} - {self.agent_id} ({self.created_at})"
```

**Fields**:
- `user` (ForeignKey, nullable): Links to the user (if available)
- `session` (ForeignKey, nullable): Links to the session (if available)
- `agent_id` (CharField, 128): Agent identifier
- `error_type` (CharField, 100): Type of error
- `error_message` (TextField): Error message
- `error_code` (CharField, 50): Error code if available
- `stack_trace` (TextField): Stack trace if available
- `context` (JSONField): Error context and metadata
- `is_resolved` (BooleanField): Whether the error has been resolved
- `resolved_at` (DateTimeField, nullable): When the error was resolved

**Indexes**:
- `agent_id`, `error_type` - For error analysis
- `-created_at` - For recent errors ordering
- `is_resolved` - For unresolved errors filtering

## Database Schema

### Relationships
```
User
├── AgentOSSession (1:N)
│   ├── AgentOSMessage (1:N)
│   └── AgentOSError (1:N)
├── AgentOSUsage (1:N)
└── AgentOSError (1:N)

AgentOSPerformance (standalone)
```

### Migration History
- **0004_agentosperformance_agentossession_agentosmessage_and_more.py**: Initial AgentOS models creation

## Usage Patterns

### Session Management
```python
# Create a new session
session = AgentOSSession.objects.create(
    user=request.user,
    agent_id="agent_123",
    agent_name="My Assistant",
    session_id="session_456",
    title="Customer Support Chat"
)

# Add messages to session
message = AgentOSMessage.objects.create(
    session=session,
    message_id="msg_789",
    role="user",
    content="Hello, I need help",
    tokens_used=10,
    cost=0.0001
)
```

### Usage Tracking
```python
# Track daily usage
usage, created = AgentOSUsage.objects.get_or_create(
    user=user,
    agent_id="agent_123",
    date=timezone.now().date(),
    defaults={
        'session_count': 1,
        'message_count': 5,
        'total_tokens': 100,
        'total_cost': 0.01
    }
)
```

### Performance Monitoring
```python
# Record performance metrics
performance = AgentOSPerformance.objects.create(
    agent_id="agent_123",
    date=timezone.now().date(),
    total_sessions=10,
    successful_sessions=9,
    failed_sessions=1,
    avg_response_time_ms=1500,
    user_satisfaction_score=4.5
)
```

## Integration with Agno

These models work alongside the Agno library by:

1. **Session Persistence**: Storing Agno session data in the database
2. **Message History**: Tracking all messages for analytics and debugging
3. **Usage Analytics**: Monitoring token usage, costs, and performance
4. **Error Tracking**: Capturing and managing errors from Agno operations
5. **User Management**: Linking Agno sessions to Django users

## Future Enhancements

### Potential Additions
- **AgentOSKnowledge**: Track knowledge base usage
- **AgentOSTool**: Track tool usage and performance
- **AgentOSFeedback**: User feedback and ratings
- **AgentOSWorkflow**: Multi-step agent workflows

### Performance Optimizations
- **Partitioning**: Date-based partitioning for large tables
- **Archiving**: Move old data to archive tables
- **Caching**: Redis caching for frequently accessed metrics
- **Aggregation**: Pre-computed daily/weekly/monthly summaries

## Maintenance

### Data Retention
- **Sessions**: Keep for 1 year, then archive
- **Messages**: Keep for 6 months, then archive
- **Usage**: Keep for 2 years for analytics
- **Performance**: Keep for 1 year
- **Errors**: Keep for 6 months, then delete

### Cleanup Tasks
```python
# Example cleanup management command
from datetime import timedelta
from django.utils import timezone

# Archive old sessions
old_sessions = AgentOSSession.objects.filter(
    created_at__lt=timezone.now() - timedelta(days=365)
)
# Archive logic here...
```

## Security Considerations

### Data Protection
- **PII Handling**: Message content may contain PII
- **Access Control**: User-based access to sessions and messages
- **Encryption**: Consider encrypting sensitive message content
- **Audit Trail**: Track who accessed what data when

### Privacy Compliance
- **GDPR**: Right to deletion, data portability
- **CCPA**: Data access and deletion rights
- **Retention Policies**: Automatic data purging
- **Consent Management**: User consent for data collection
