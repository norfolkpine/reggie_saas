from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Debug authentication configuration and token issues"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-tokens",
            action="store_true",
            help="Check JWT token configuration",
        )
        parser.add_argument(
            "--check-sessions",
            action="store_true",
            help="Check session configuration",
        )
        parser.add_argument(
            "--check-oidc",
            action="store_true",
            help="Check OIDC configuration",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run all checks",
        )

    def handle(self, *args, **options):
        if options["all"] or not any([options["check_tokens"], options["check_sessions"], options["check_oidc"]]):
            self.check_tokens()
            self.check_sessions()
            self.check_oidc()
        else:
            if options["check_tokens"]:
                self.check_tokens()
            if options["check_sessions"]:
                self.check_sessions()
            if options["check_oidc"]:
                self.check_oidc()

    def check_tokens(self):
        self.stdout.write(self.style.SUCCESS("\n=== JWT Token Configuration ==="))

        jwt_config = getattr(settings, "SIMPLE_JWT", {})

        self.stdout.write(f"Access Token Lifetime: {jwt_config.get('ACCESS_TOKEN_LIFETIME', 'Not set')}")
        self.stdout.write(f"Refresh Token Lifetime: {jwt_config.get('REFRESH_TOKEN_LIFETIME', 'Not set')}")
        self.stdout.write(f"Rotate Refresh Tokens: {jwt_config.get('ROTATE_REFRESH_TOKENS', 'Not set')}")
        self.stdout.write(f"Blacklist After Rotation: {jwt_config.get('BLACKLIST_AFTER_ROTATION', 'Not set')}")

        # Check if token lifetimes are reasonable
        access_lifetime = jwt_config.get("ACCESS_TOKEN_LIFETIME")
        if access_lifetime and access_lifetime < timedelta(hours=1):
            self.stdout.write(self.style.WARNING(f"⚠️  Access token lifetime is very short: {access_lifetime}"))
        elif access_lifetime:
            self.stdout.write(self.style.SUCCESS(f"✅ Access token lifetime looks good: {access_lifetime}"))

    def check_sessions(self):
        self.stdout.write(self.style.SUCCESS("\n=== Session Configuration ==="))

        self.stdout.write(f"Session Cookie Age: {getattr(settings, 'SESSION_COOKIE_AGE', 'Not set')} seconds")
        self.stdout.write(
            f"Session Expire at Browser Close: {getattr(settings, 'SESSION_EXPIRE_AT_BROWSER_CLOSE', 'Not set')}"
        )
        self.stdout.write(f"Session Save Every Request: {getattr(settings, 'SESSION_SAVE_EVERY_REQUEST', 'Not set')}")
        self.stdout.write(f"Session Cookie Secure: {getattr(settings, 'SESSION_COOKIE_SECURE', 'Not set')}")

        # Check session age
        session_age = getattr(settings, "SESSION_COOKIE_AGE", 0)
        if session_age < 86400:  # Less than 1 day
            self.stdout.write(self.style.WARNING(f"⚠️  Session cookie age is very short: {session_age} seconds"))
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Session cookie age looks good: {session_age} seconds"))

    def check_oidc(self):
        self.stdout.write(self.style.SUCCESS("\n=== OIDC Configuration ==="))

        oidc_settings = [
            "OIDC_RP_CLIENT_ID",
            "OIDC_RP_CLIENT_SECRET",
            "OIDC_OP_AUTHORIZATION_ENDPOINT",
            "OIDC_OP_TOKEN_ENDPOINT",
            "OIDC_OP_USER_ENDPOINT",
            "OIDC_OP_LOGOUT_ENDPOINT",
        ]

        for setting in oidc_settings:
            value = getattr(settings, setting, None)
            if value:
                # Mask sensitive values
                if "SECRET" in setting or "CLIENT_SECRET" in setting:
                    display_value = value[:8] + "***" if len(value) > 8 else "***"
                else:
                    display_value = value
                self.stdout.write(f"{setting}: {display_value}")
            else:
                self.stdout.write(self.style.WARNING(f"⚠️  {setting}: Not configured"))

        # Check authentication backends
        auth_backends = getattr(settings, "AUTHENTICATION_BACKENDS", [])
        self.stdout.write(f"\nAuthentication Backends: {auth_backends}")

        if "apps.authentication.backends.CustomOIDCAuthenticationBackend" in auth_backends:
            self.stdout.write(self.style.SUCCESS("✅ OIDC backend is configured"))
        else:
            self.stdout.write(self.style.WARNING("⚠️  OIDC backend is not configured"))

    def check_user_sessions(self):
        self.stdout.write(self.style.SUCCESS("\n=== User Session Analysis ==="))

        # Count active users
        active_users = User.objects.filter(is_active=True).count()
        self.stdout.write(f"Active users: {active_users}")

        # Check for users with recent activity (you might need to add a last_activity field)
        self.stdout.write("Note: Add a last_activity field to User model for better session tracking")
