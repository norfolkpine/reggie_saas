# User Impersonation System

This document explains how to use the user impersonation system in the Reggie SaaS application. This feature allows superusers to temporarily log in as other users for debugging, support, and testing purposes.

## Overview

The user impersonation system consists of:
- **Backend API endpoints** (Django)
- **React components** for the user interface
- **Custom hooks** for programmatic access
- **Security controls** to ensure only authorized users can impersonate

## Security & Permissions

⚠️ **Important Security Notes:**
- Only **superusers** can impersonate other users
- This feature should be used responsibly and only for legitimate purposes
- All impersonation actions are logged and tracked
- Users are clearly notified when they are being impersonated

## Backend API Endpoints

### 1. Start User Impersonation
**Endpoint:** `POST /support/api/hijack/`

**Request Body:**
```json
{
  "user_id": 123
}
```

**Response:**
```json
{
  "success": true,
  "message": "Now impersonating user@example.com",
  "impersonated_user": {
    "id": 123,
    "email": "user@example.com",
    "full_name": "John Doe"
  }
}
```

**Permissions:** Requires superuser status

### 2. Stop User Impersonation
**Endpoint:** `POST /support/api/stop-hijack/`

**Request Body:** None required

**Response:**
```json
{
  "success": true,
  "message": "Stopped impersonating, back to admin@example.com",
  "original_user": {
    "id": 1,
    "email": "admin@example.com",
    "full_name": "Admin User"
  }
}
```

**Permissions:** Requires authentication

### 3. Check Impersonation Status
**Endpoint:** `GET /support/api/status/`

**Response:**
```json
{
  "is_impersonating": true,
  "impersonated_user": {
    "id": 123,
    "email": "user@example.com",
    "full_name": "John Doe"
  },
  "original_user": {
    "id": 1,
    "email": "admin@example.com",
    "full_name": "Admin User"
  }
}
```

**Permissions:** Requires authentication

## Frontend Usage

### 1. Full User Impersonation Component

The `UserImpersonation` component provides a complete interface for user impersonation:

```tsx
import UserImpersonation from './components/UserImpersonation';

function AdminPanel() {
  return (
    <div className="admin-panel">
      <h1>Admin Panel</h1>
      
      {/* User Impersonation Section */}
      <section className="impersonation-section">
        <h2>User Management</h2>
        <UserImpersonation />
      </section>
    </div>
  );
}
```

**Features:**
- Dropdown to select users for impersonation
- Start/stop impersonation controls
- Real-time status display
- Error handling and loading states
- Responsive design with Tailwind CSS

### 2. Simple Impersonation Button

For quick access, use the `ImpersonationButton` component:

```tsx
import ImpersonationButton from './components/ImpersonationButton';

function UserList({ users }) {
  return (
    <div className="user-list">
      {users.map(user => (
        <div key={user.id} className="user-item">
          <div className="user-info">
            <span className="user-email">{user.email}</span>
            <span className="user-name">{user.full_name}</span>
          </div>
          
          <div className="user-actions">
            <ImpersonationButton 
              user={user} 
              variant="outline" 
              size="sm" 
            />
          </div>
        </div>
      ))}
    </div>
  );
}
```

**Button Variants:**
- `primary` - Blue button (default)
- `secondary` - Gray button
- `outline` - Outlined button

**Button Sizes:**
- `sm` - Small
- `md` - Medium (default)
- `lg` - Large

### 3. Custom Hook for Advanced Usage

For custom implementations, use the `useUserImpersonation` hook:

```tsx
import { useUserImpersonation } from './hooks/useUserImpersonation';

function CustomImpersonationControl() {
  const {
    isImpersonating,
    impersonatedUser,
    originalUser,
    loading,
    error,
    startImpersonation,
    stopImpersonation,
    clearError
  } = useUserImpersonation();

  const handleImpersonate = async (userId) => {
    const success = await startImpersonation(userId);
    if (success) {
      console.log('Impersonation started successfully');
    }
  };

  return (
    <div className="custom-control">
      {error && (
        <div className="error-message">
          {error}
          <button onClick={clearError}>Dismiss</button>
        </div>
      )}
      
      {isImpersonating ? (
        <div className="impersonation-status">
          <p>Currently impersonating: {impersonatedUser?.email}</p>
          <button 
            onClick={stopImpersonation}
            disabled={loading}
          >
            {loading ? 'Stopping...' : 'Stop Impersonation'}
          </button>
        </div>
      ) : (
        <div className="start-impersonation">
          <button 
            onClick={() => handleImpersonate(123)}
            disabled={loading}
          >
            {loading ? 'Starting...' : 'Impersonate User 123'}
          </button>
        </div>
      )}
    </div>
  );
}
```

## Implementation Examples

### Example 1: Admin Dashboard Integration

```tsx
import React from 'react';
import UserImpersonation from './components/UserImpersonation';

function AdminDashboard() {
  return (
    <div className="admin-dashboard">
      <header className="dashboard-header">
        <h1>Admin Dashboard</h1>
        <nav className="dashboard-nav">
          <a href="#users">Users</a>
          <a href="#analytics">Analytics</a>
          <a href="#settings">Settings</a>
        </nav>
      </header>
      
      <main className="dashboard-content">
        <section className="impersonation-section">
          <h2>User Impersonation</h2>
          <p className="text-gray-600 mb-4">
            Use this tool to temporarily log in as another user for support purposes.
          </p>
          <UserImpersonation />
        </section>
        
        {/* Other dashboard sections */}
      </main>
    </div>
  );
}
```

### Example 2: User Management Table

```tsx
import React from 'react';
import ImpersonationButton from './components/ImpersonationButton';

function UserManagementTable({ users }) {
  return (
    <div className="user-management">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              User
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {users.map((user) => (
            <tr key={user.id}>
              <td className="px-6 py-4 whitespace-nowrap">
                <div className="flex items-center">
                  <div className="flex-shrink-0 h-10 w-10">
                    <img 
                      className="h-10 w-10 rounded-full" 
                      src={user.avatar_url} 
                      alt="" 
                    />
                  </div>
                  <div className="ml-4">
                    <div className="text-sm font-medium text-gray-900">
                      {user.full_name}
                    </div>
                    <div className="text-sm text-gray-500">
                      {user.email}
                    </div>
                  </div>
                </div>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                  user.is_active 
                    ? 'bg-green-100 text-green-800' 
                    : 'bg-red-100 text-red-800'
                }`}>
                  {user.is_active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                <ImpersonationButton 
                  user={user} 
                  variant="outline" 
                  size="sm" 
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Example 3: Support Ticket Interface

```tsx
import React from 'react';
import { useUserImpersonation } from './hooks/useUserImpersonation';

function SupportTicket({ ticket }) {
  const { startImpersonation, isImpersonating } = useUserImpersonation();

  const handleImpersonateUser = async () => {
    await startImpersonation(ticket.user.id);
  };

  return (
    <div className="support-ticket">
      <div className="ticket-header">
        <h3 className="ticket-title">#{ticket.id} - {ticket.title}</h3>
        <div className="ticket-meta">
          <span className="ticket-user">Reported by: {ticket.user.email}</span>
          <span className="ticket-date">{ticket.created_at}</span>
        </div>
      </div>
      
      <div className="ticket-content">
        <p>{ticket.description}</p>
      </div>
      
      <div className="ticket-actions">
        {!isImpersonating && (
          <button
            onClick={handleImpersonateUser}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md"
          >
            Impersonate User to Debug
          </button>
        )}
        
        <button className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-md">
          Reply to Ticket
        </button>
      </div>
    </div>
  );
}
```

## Styling and Customization

### Tailwind CSS Classes

The components use Tailwind CSS for styling. You can customize the appearance by:

1. **Modifying the component's className prop:**
```tsx
<UserImpersonation className="custom-impersonation-panel" />
```

2. **Using CSS custom properties:**
```css
.custom-impersonation-panel {
  --impersonation-primary: #3b82f6;
  --impersonation-secondary: #6b7280;
  --impersonation-danger: #ef4444;
}
```

3. **Overriding with your own CSS:**
```css
.impersonation-button {
  @apply bg-custom-blue hover:bg-custom-blue-dark;
}
```

### Responsive Design

All components are responsive and work on:
- Desktop (1024px+)
- Tablet (768px - 1023px)
- Mobile (< 768px)

## Error Handling

The system provides comprehensive error handling:

```tsx
// Error states are automatically managed
const { error, clearError } = useUserImpersonation();

// Display errors to users
{error && (
  <div className="error-banner">
    <span>{error}</span>
    <button onClick={clearError}>×</button>
  </div>
)}
```

**Common Error Scenarios:**
- User not found
- Insufficient permissions
- Network errors
- Session expired

## Testing

### Unit Tests

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import UserImpersonation from './components/UserImpersonation';

describe('UserImpersonation', () => {
  it('should start impersonation when user is selected', async () => {
    render(<UserImpersonation />);
    
    const select = screen.getByLabelText(/select user/i);
    fireEvent.change(select, { target: { value: '123' } });
    
    const button = screen.getByText(/start impersonation/i);
    fireEvent.click(button);
    
    await waitFor(() => {
      expect(screen.getByText(/starting impersonation/i)).toBeInTheDocument();
    });
  });
});
```

### Integration Tests

```tsx
import { render, screen } from '@testing-library/react';
import { useUserImpersonation } from './hooks/useUserImpersonation';

// Mock the hook
jest.mock('./hooks/useUserImpersonation');

function TestComponent() {
  const { isImpersonating, startImpersonation } = useUserImpersonation();
  
  return (
    <div>
      {isImpersonating ? 'Impersonating' : 'Not Impersonating'}
      <button onClick={() => startImpersonation(123)}>Impersonate</button>
    </div>
  );
}
```

## Troubleshooting

### Common Issues

1. **"Only superusers can impersonate users" error**
   - Ensure the current user has superuser privileges
   - Check Django admin panel for user permissions

2. **CSRF token errors**
   - Verify CSRF middleware is enabled
   - Check that cookies are being sent with requests

3. **Page not refreshing after impersonation**
   - Ensure `window.location.reload()` is not blocked
   - Check browser console for JavaScript errors

4. **Session not persisting**
   - Verify Django session configuration
   - Check Redis/cache configuration if using session storage

### Debug Mode

Enable debug logging by setting the environment variable:
```bash
DEBUG_IMPERSONATION=true
```

This will log all impersonation actions to the console.

## Best Practices

1. **Use Responsibly**
   - Only impersonate users when necessary
   - Always inform users when impersonation is active
   - Log all impersonation actions

2. **Security Considerations**
   - Regularly audit impersonation logs
   - Implement time limits for impersonation sessions
   - Consider requiring additional authentication for sensitive operations

3. **User Experience**
   - Provide clear visual indicators when impersonating
   - Make it easy to stop impersonation
   - Preserve user context when possible

4. **Performance**
   - Cache user lists to avoid repeated API calls
   - Implement proper loading states
   - Use optimistic updates where appropriate

## API Reference

### Types

```typescript
interface User {
  id: number;
  email: string;
  full_name: string;
}

interface ImpersonationState {
  isImpersonating: boolean;
  impersonatedUser: User | null;
  originalUser: User | null;
}

interface ImpersonationResponse {
  success: boolean;
  message: string;
  impersonated_user?: User;
  original_user?: User;
}
```

### Hook Return Values

```typescript
const {
  // State
  isImpersonating: boolean,
  impersonatedUser: User | null,
  originalUser: User | null,
  
  // Actions
  startImpersonation: (userId: number) => Promise<boolean>,
  stopImpersonation: () => Promise<boolean>,
  
  // Utilities
  loading: boolean,
  error: string,
  clearError: () => void,
} = useUserImpersonation();
```

## Support

For issues or questions about the user impersonation system:

1. Check the Django logs for backend errors
2. Review browser console for frontend errors
3. Verify user permissions and authentication
4. Contact the development team with specific error messages

---

**Note:** This feature is intended for legitimate administrative and support purposes only. Misuse may result in account suspension or other disciplinary action.
