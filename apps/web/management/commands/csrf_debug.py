from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Debug CSRF configuration and settings"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🔍 CSRF Configuration Debug"))
        self.stdout.write("=" * 50)

        # CSRF Middleware status
        csrf_middleware = "django.middleware.csrf.CsrfViewMiddleware"
        if csrf_middleware in settings.MIDDLEWARE:
            self.stdout.write("✅ CSRF Middleware: ENABLED")
        else:
            self.stdout.write("❌ CSRF Middleware: DISABLED")

        # CSRF Settings
        self.stdout.write("\n📋 CSRF Settings:")
        self.stdout.write(f"  CSRF_TRUSTED_ORIGINS: {getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])}")
        self.stdout.write(f"  CSRF_COOKIE_DOMAIN: {getattr(settings, 'CSRF_COOKIE_DOMAIN', 'Not set')}")
        self.stdout.write(f"  CSRF_COOKIE_SAMESITE: {getattr(settings, 'CSRF_COOKIE_SAMESITE', 'Not set')}")
        self.stdout.write(f"  CSRF_COOKIE_SECURE: {getattr(settings, 'CSRF_COOKIE_SECURE', 'Not set')}")
        self.stdout.write(f"  CSRF_COOKIE_HTTPONLY: {getattr(settings, 'CSRF_COOKIE_HTTPONLY', 'Not set')}")
        self.stdout.write(f"  CSRF_USE_SESSIONS: {getattr(settings, 'CSRF_USE_SESSIONS', 'Not set')}")

        # Environment info
        self.stdout.write("\n🌍 Environment:")
        self.stdout.write(f"  DEBUG: {settings.DEBUG}")
        self.stdout.write(f"  FRONTEND_ADDRESS: {getattr(settings, 'FRONTEND_ADDRESS', 'Not set')}")

        # CORS Settings
        self.stdout.write("\n🔗 CORS Settings:")
        self.stdout.write(f"  CORS_ALLOWED_ORIGINS: {getattr(settings, 'CORS_ALLOWED_ORIGINS', [])}")
        self.stdout.write(f"  CORS_ALLOW_CREDENTIALS: {getattr(settings, 'CORS_ALLOW_CREDENTIALS', 'Not set')}")

        # Recommendations
        self.stdout.write("\n💡 Recommendations:")
        if settings.DEBUG:
            self.stdout.write("  • You're in DEBUG mode - CSRF should be more permissive")
            self.stdout.write("  • Check that your frontend origin is in CSRF_TRUSTED_ORIGINS")
            self.stdout.write("  • Ensure your frontend is sending the CSRF token in requests")
            self.stdout.write("  • Use the csrf-test endpoint at /csrf-test/ to verify functionality")
        else:
            self.stdout.write("  • You're in PRODUCTION mode - CSRF should be strict")
            self.stdout.write("  • Ensure CSRF_COOKIE_SECURE is True for HTTPS")
            self.stdout.write("  • Verify CSRF_TRUSTED_ORIGINS contains your production domains")

        self.stdout.write("\n🔧 To disable CSRF in development (NOT recommended):")
        self.stdout.write("  Set DISABLE_CSRF_IN_DEV=true in your .env file")
        self.stdout.write("  This will remove the CSRF middleware entirely")

        self.stdout.write("\n📚 For more help, visit:")
        self.stdout.write("  • /csrf-debug/ - Detailed CSRF debugging page")
        self.stdout.write("  • /csrf-test/ - Test CSRF functionality")
        self.stdout.write("  • /csrf-exempt-test/ - Test CSRF-exempt endpoint")
