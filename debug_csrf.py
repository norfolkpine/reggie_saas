#!/usr/bin/env python
"""
Debug script to check CSRF configuration and environment variables.
Run this to see what's happening with your CSRF setup.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bh_reggie.settings')

# Import Django and check settings
try:
    import django
    django.setup()
    
    from django.conf import settings
    from django.middleware.csrf import get_token
    from django.http import HttpRequest
    
    print("🔍 CSRF Configuration Debug")
    print("=" * 50)
    
    # Check environment variables
    print("\n🌍 Environment Variables:")
    frontend_address = os.environ.get('FRONTEND_ADDRESS')
    print(f"  FRONTEND_ADDRESS: {frontend_address}")
    
    # Check Django settings
    print("\n📋 Django Settings:")
    print(f"  DEBUG: {settings.DEBUG}")
    print(f"  FRONTEND_ADDRESS: {getattr(settings, 'FRONTEND_ADDRESS', 'Not set')}")
    print(f"  CSRF_TRUSTED_ORIGINS: {getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])}")
    print(f"  CSRF_COOKIE_SAMESITE: {getattr(settings, 'CSRF_COOKIE_SAMESITE', 'Not set')}")
    print(f"  CSRF_COOKIE_SECURE: {getattr(settings, 'CSRF_COOKIE_SECURE', 'Not set')}")
    print(f"  CSRF_COOKIE_HTTPONLY: {getattr(settings, 'CSRF_COOKIE_HTTPONLY', 'Not set')}")
    
    # Check CORS settings
    print("\n🔗 CORS Settings:")
    print(f"  CORS_ALLOWED_ORIGINS: {getattr(settings, 'CORS_ALLOWED_ORIGINS', [])}")
    print(f"  CORS_ALLOW_CREDENTIALS: {getattr(settings, 'CORS_ALLOW_CREDENTIALS', 'Not set')}")
    
    # Check middleware
    print("\n⚙️  Middleware:")
    csrf_middleware = "django.middleware.csrf.CsrfViewMiddleware"
    if csrf_middleware in settings.MIDDLEWARE:
        print(f"  ✅ CSRF Middleware: ENABLED")
    else:
        print(f"  ❌ CSRF Middleware: DISABLED")
    
    # Recommendations
    print("\n💡 Recommendations:")
    if settings.DEBUG:
        print("  • You're in DEBUG mode - CSRF should be more permissive")
        print("  • Check that your frontend origin is in CSRF_TRUSTED_ORIGINS")
        print("  • Ensure your frontend is sending the CSRF token in requests")
        
        # Check for common issues
        if not getattr(settings, 'CSRF_TRUSTED_ORIGINS', []):
            print("  ❌ CSRF_TRUSTED_ORIGINS is empty - this will cause CSRF failures")
        
        if getattr(settings, 'CSRF_COOKIE_SAMESITE', None) is None:
            print("  ❌ CSRF_COOKIE_SAMESITE is None - should be 'Lax' in development")
            
    else:
        print("  • You're in PRODUCTION mode - CSRF should be strict")
    
    print("\n🔧 To fix common issues:")
    print("  1. Ensure FRONTEND_ADDRESS is set in your environment")
    print("  2. Check that your frontend origin is in CSRF_TRUSTED_ORIGINS")
    print("  3. Verify CSRF_COOKIE_SAMESITE is set to 'Lax' in development")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nThis might mean Django isn't properly configured.")
    print("Try running this from your Django project directory.")
