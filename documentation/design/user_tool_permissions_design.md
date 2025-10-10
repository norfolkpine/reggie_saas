# User Tool Permissions Design

## Overview

This document outlines the design for a comprehensive per-user tool permission system that allows fine-grained control over which tools each user can access in the AI agent system.

## Problem Statement

Currently, the `Toolkit` class provides basic filtering mechanisms (`include_tools`, `exclude_tools`) but these are set at the toolkit level, not per-user. We need a system that allows:

1. **Per-user tool restrictions** - Different users should have access to different tools
2. **Team-based permissions** - Tools can be restricted by team membership
3. **Time-based restrictions** - Tools can have expiration dates
4. **Usage limits** - Tools can have usage quotas
5. **Easy administration** - Simple interface for managing permissions
6. **Default templates** - Automatic permission assignment for new users

## Architecture

### Core Components

#### 1. UserToolPermission Model

```python
class UserToolPermission(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tool_name = models.CharField(max_length=100)
    tool_category = models.CharField(max_length=50, choices=TOOL_CATEGORIES)
    is_allowed = models.BooleanField(default=True)
    team = models.ForeignKey('teams.Team', null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
```

**Key Features:**
- Per-user, per-tool permissions
- Team-scoped permissions (optional)
- Time-based expiration
- Usage quotas with tracking
- Admin notes for audit trail

#### 2. ToolPermissionTemplate Model

```python
class ToolPermissionTemplate(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    tool_permissions = models.JSONField(default=dict)
    is_default_for_new_users = models.BooleanField(default=False)
    is_default_for_new_teams = models.BooleanField(default=False)
```

**Key Features:**
- Predefined permission sets
- Automatic application to new users/teams
- JSON configuration for flexibility

#### 3. ToolFilter Class

```python
class ToolFilter:
    def __init__(self, user: User, team=None):
        self.user = user
        self.team = team
        self._permission_cache = {}
    
    def filter_tools(self, tools: List[Any]) -> List[Any]:
        # Filter tools based on user permissions
        pass
    
    def can_access_tool(self, tool_name: str) -> bool:
        # Check if user can access specific tool
        pass
```

**Key Features:**
- Caching for performance
- Team-aware filtering
- Easy integration with existing code

## Implementation Details

### 1. Database Schema

#### UserToolPermission Table
```sql
CREATE TABLE opie_usertoolpermission (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_user(id),
    tool_name VARCHAR(100) NOT NULL,
    tool_category VARCHAR(50) NOT NULL,
    is_allowed BOOLEAN DEFAULT TRUE,
    team_id INTEGER REFERENCES teams_team(id),
    expires_at TIMESTAMP NULL,
    usage_limit INTEGER NULL,
    usage_count INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, tool_name, team_id)
);
```

#### ToolPermissionTemplate Table
```sql
CREATE TABLE opie_toolpermissiontemplate (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    tool_permissions JSONB DEFAULT '{}',
    is_default_for_new_users BOOLEAN DEFAULT FALSE,
    is_default_for_new_teams BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 2. Tool Categories

```python
TOOL_CATEGORIES = [
    ('file_operations', 'File Operations'),
    ('web_scraping', 'Web Scraping'),
    ('api_integrations', 'API Integrations'),
    ('database_operations', 'Database Operations'),
    ('external_services', 'External Services'),
    ('agent_operations', 'Agent Operations'),
]
```

### 3. Default Permission Templates

#### Basic User Template
```json
{
    "file_reader_tools": {"allowed": true, "category": "file_operations"},
    "googlesearch_tools": {"allowed": true, "category": "web_scraping"},
    "website_page_scraper_tools": {"allowed": true, "category": "web_scraping"},
    "coingecko_tools": {"allowed": true, "category": "api_integrations"},
    "blockscout_tools": {"allowed": true, "category": "api_integrations"},
    "jules_api_tools": {"allowed": true, "category": "api_integrations"},
    "run_agent_tool": {"allowed": true, "category": "agent_operations"},
    "jira_tools": {"allowed": false, "category": "api_integrations"},
    "confluence_tools": {"allowed": false, "category": "api_integrations"}
}
```

#### Admin User Template
```json
{
    "file_reader_tools": {"allowed": true, "category": "file_operations"},
    "googlesearch_tools": {"allowed": true, "category": "web_scraping"},
    "website_page_scraper_tools": {"allowed": true, "category": "web_scraping"},
    "coingecko_tools": {"allowed": true, "category": "api_integrations"},
    "blockscout_tools": {"allowed": true, "category": "api_integrations"},
    "jules_api_tools": {"allowed": true, "category": "api_integrations"},
    "run_agent_tool": {"allowed": true, "category": "agent_operations"},
    "jira_tools": {"allowed": true, "category": "api_integrations"},
    "confluence_tools": {"allowed": true, "category": "api_integrations"}
}
```

#### Restricted User Template
```json
{
    "file_reader_tools": {"allowed": true, "category": "file_operations"},
    "googlesearch_tools": {"allowed": false, "category": "web_scraping"},
    "website_page_scraper_tools": {"allowed": false, "category": "web_scraping"},
    "coingecko_tools": {"allowed": false, "category": "api_integrations"},
    "blockscout_tools": {"allowed": false, "category": "api_integrations"},
    "jules_api_tools": {"allowed": false, "category": "api_integrations"},
    "run_agent_tool": {"allowed": false, "category": "agent_operations"},
    "jira_tools": {"allowed": false, "category": "api_integrations"},
    "confluence_tools": {"allowed": false, "category": "api_integrations"}
}
```

## Integration Points

### 1. AgentBuilder Integration

The `AgentBuilder.build()` method is updated to include tool filtering:

```python
def build(self, enable_reasoning: bool | None = None) -> Agent:
    # ... existing code ...
    
    # === Apply user-specific tool filtering ===
    user_team = self._get_user_team()
    tool_filter = ToolFilter(user=self.user, team=user_team)
    tools = tool_filter.filter_tools(tools)
    
    # ... rest of agent creation ...
```

### 2. Django Admin Integration

Custom admin interface with:
- Bulk permission management
- Template application
- Usage statistics
- Permission auditing

### 3. Management Commands

```bash
# Set up default permissions
python manage.py setup_tool_permissions

# Apply template to specific user
python manage.py setup_tool_permissions --user-email user@example.com --template admin

# Apply template to team
python manage.py setup_tool_permissions --team-slug engineering --template basic

# Apply to all existing users
python manage.py setup_tool_permissions --apply-to-existing-users --template basic
```

### 4. Django Signals

Automatic permission assignment:
- New users get default template
- New team members get team template
- Permission expiration handling

## Usage Examples

### 1. Basic Usage

```python
# Check if user can access a tool
tool_filter = ToolFilter(user=request.user)
if tool_filter.can_access_tool('jira_tools'):
    # User can use Jira tools
    pass

# Filter tools for user
allowed_tools = tool_filter.filter_tools(all_tools)
```

### 2. Team-Scoped Permissions

```python
# Check permission within team context
tool_filter = ToolFilter(user=request.user, team=request.team)
if tool_filter.can_access_tool('jira_tools'):
    # User can use Jira tools within this team
    pass
```

### 3. Admin Management

```python
# Create permission for user
UserToolPermission.objects.create(
    user=user,
    tool_name='jira_tools',
    tool_category='api_integrations',
    is_allowed=True,
    team=team,
    usage_limit=100
)

# Apply template to user
template = ToolPermissionTemplate.objects.get(name='Admin User')
template.apply_to_user(user, team)
```

## Performance Considerations

### 1. Caching Strategy

- **Permission Cache**: In-memory cache for user permissions
- **Template Cache**: Cache for permission templates
- **Database Indexes**: Optimized queries for permission checks

### 2. Database Optimization

```sql
-- Indexes for performance
CREATE INDEX idx_usertoolpermission_user_tool ON opie_usertoolpermission(user_id, tool_name);
CREATE INDEX idx_usertoolpermission_tool_allowed ON opie_usertoolpermission(tool_name, is_allowed);
CREATE INDEX idx_usertoolpermission_team ON opie_usertoolpermission(team_id);
CREATE INDEX idx_usertoolpermission_expires ON opie_usertoolpermission(expires_at);
```

### 3. Query Optimization

- Use `select_related()` for foreign keys
- Batch permission checks
- Cache frequently accessed permissions

## Security Considerations

### 1. Permission Inheritance

1. **User-specific permissions** override templates
2. **Team permissions** override global permissions
3. **Most restrictive** permission wins

### 2. Audit Trail

- Track permission changes
- Log tool usage
- Monitor permission violations

### 3. Data Protection

- Encrypt sensitive permission data
- Regular permission audits
- Access logging

## Migration Strategy

### Phase 1: Core Implementation
1. Create models and migrations
2. Implement ToolFilter class
3. Update AgentBuilder
4. Create admin interface

### Phase 2: Default Setup
1. Create default templates
2. Set up management commands
3. Apply to existing users
4. Test with sample users

### Phase 3: Advanced Features
1. Usage tracking
2. Permission analytics
3. Bulk management tools
4. API endpoints

### Phase 4: Optimization
1. Performance tuning
2. Caching implementation
3. Database optimization
4. Monitoring setup

## API Design

### 1. Permission Check Endpoint

```python
GET /api/tool-permissions/check/
{
    "tool_name": "jira_tools",
    "user_id": 123,
    "team_id": 456
}

Response:
{
    "allowed": true,
    "expires_at": "2024-12-31T23:59:59Z",
    "usage_remaining": 95,
    "usage_limit": 100
}
```

### 2. User Tools Endpoint

```python
GET /api/tool-permissions/user-tools/
{
    "user_id": 123,
    "team_id": 456
}

Response:
{
    "tools": [
        {
            "name": "jira_tools",
            "category": "api_integrations",
            "allowed": true,
            "usage_remaining": 95,
            "usage_limit": 100
        }
    ]
}
```

## Testing Strategy

### 1. Unit Tests

- Model validation
- Permission logic
- Template application
- Filter functionality

### 2. Integration Tests

- AgentBuilder integration
- Admin interface
- Management commands
- API endpoints

### 3. Performance Tests

- Permission check performance
- Bulk operations
- Cache effectiveness
- Database query optimization

## Monitoring and Analytics

### 1. Key Metrics

- Permission check frequency
- Tool usage patterns
- Permission violation attempts
- Template application rates

### 2. Alerts

- High permission denial rates
- Unusual tool usage patterns
- Permission expiration warnings
- System performance issues

### 3. Reporting

- User tool access reports
- Team permission summaries
- Usage analytics
- Security audit reports

## Future Enhancements

### 1. Advanced Features

- **Role-based permissions**: Group users by roles
- **Conditional permissions**: Time-based or context-based access
- **Permission workflows**: Approval processes for sensitive tools
- **Integration permissions**: External system access control

### 2. User Experience

- **Self-service portal**: Users can request tool access
- **Permission dashboard**: Visual tool access overview
- **Usage analytics**: Personal tool usage statistics
- **Recommendation engine**: Suggest relevant tools

### 3. Enterprise Features

- **SSO integration**: Single sign-on permission sync
- **Compliance reporting**: Audit trail for regulations
- **Multi-tenant support**: Isolated permission spaces
- **Advanced analytics**: Machine learning insights

## Conclusion

This design provides a comprehensive, scalable solution for per-user tool permissions that:

1. **Maintains performance** through caching and optimization
2. **Provides flexibility** through templates and fine-grained control
3. **Ensures security** through proper permission inheritance
4. **Enables administration** through intuitive interfaces
5. **Supports growth** through enterprise-ready features

The implementation can be done incrementally, starting with core functionality and adding advanced features over time.

