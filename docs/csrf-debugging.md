# CSRF Debugging Guide

This guide helps you troubleshoot CSRF (Cross-Site Request Forgery) issues in your Django application.

## Quick Start

### 1. Check CSRF Configuration
Run the management command to see your current CSRF setup:
```bash
python manage.py csrf_debug
```

### 2. Visit Debug Pages
- **CSRF Debug Page**: `/csrf-debug/` - Comprehensive CSRF information
- **CSRF Test**: `/csrf-test/` - Test CSRF protection
- **CSRF Exempt Test**: `/csrf-exempt-test/` - Test CSRF-exempt endpoint

## Common CSRF Issues & Solutions

### Issue: "CSRF verification failed. Request aborted."

#### Solution 1: Check Trusted Origins
Ensure your frontend origin is in `CSRF_TRUSTED_ORIGINS`:

```python
# In settings.py
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",      # React dev server
    "http://localhost:5173",      # Vite dev server
    "http://localhost:8000",      # Django dev server
    "http://127.0.0.1:8000",     # Django dev server (alternative)
]
```

#### Solution 2: Verify Cookie Settings
For development, ensure these settings:

```python
# In settings.py (development)
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
```

#### Solution 3: Frontend CSRF Token
Include CSRF token in your requests:

**Django Templates:**
```html
<form method="POST">
    {% csrf_token %}
    <!-- form fields -->
</form>
```

**JavaScript/AJAX:**
```javascript
// Get token from cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Include in fetch requests
fetch('/api/endpoint/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
    },
    credentials: 'include',
    body: JSON.stringify(data)
});
```

## Development vs Production

### Development Settings
```python
if DEBUG:
    CSRF_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SECURE = False
    CSRF_COOKIE_HTTPONLY = False
    
    # Add development origins
    CSRF_TRUSTED_ORIGINS.extend([
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ])
```

### Production Settings
```python
# Production should be strict
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Strict"  # or "Lax" for cross-origin
CSRF_COOKIE_HTTPONLY = False  # Keep False for JavaScript access
```

## Emergency CSRF Disable (NOT RECOMMENDED)

**Only use this for extreme development cases:**

1. Set environment variable:
```bash
export DISABLE_CSRF_IN_DEV=true
```

2. Or add to `.env` file:
```env
DISABLE_CSRF_IN_DEV=true
```

**⚠️ Warning**: This completely removes CSRF protection and should NEVER be used in production.

## Testing CSRF

### 1. Manual Testing
- Visit `/csrf-test/` and submit the form
- Check browser console for any errors
- Verify CSRF token is present in form

### 2. AJAX Testing
- Use the "Test AJAX" button on `/csrf-debug/`
- Check network tab for request headers
- Verify `X-CSRFToken` header is sent

### 3. Debug Information
- Check `/csrf-debug/` for comprehensive CSRF status
- Run `python manage.py csrf_debug` for command-line info
- Look for missing trusted origins or cookie issues

## Troubleshooting Checklist

- [ ] Is your frontend origin in `CSRF_TRUSTED_ORIGINS`?
- [ ] Are you sending the CSRF token in requests?
- [ ] Is the CSRF cookie being set (check browser dev tools)?
- [ ] Are your cookie settings appropriate for your environment?
- [ ] Is CORS configured correctly for cross-origin requests?
- [ ] Are you using `credentials: 'include'` in fetch requests?

## Related Documentation

- [Django CSRF Documentation](https://docs.djangoproject.com/en/stable/ref/csrf/)
- [Django CORS Headers](https://github.com/adamchainz/django-cors-headers)
- [Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)

## Getting Help

If you're still experiencing CSRF issues:

1. Run `python manage.py csrf_debug`
2. Check `/csrf-debug/` page
3. Review browser console and network tab
4. Verify your environment variables and settings
5. Check that your frontend is properly configured for CSRF
