from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

CustomUser = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        """
        Populates user information from social provider info.
        This method is called after a successful social login, when a
        social account has been associated with a User instance.
        """
        user = super().populate_user(request, sociallogin, data)

        # OIDC claims are typically in `sociallogin.account.extra_data`
        claims = sociallogin.account.extra_data

        # Replicate logic from CustomOIDCAuthenticationBackend.update_user
        # and parts of CustomOIDCAuthenticationBackend.create_user for field population

        email = claims.get("email")
        if email:
            user.email = email

        # Ensure username is set, defaulting to email if preferred_username is not present
        # This logic is more for new user creation but good to ensure consistency
        username = claims.get("preferred_username", email)
        if username and not CustomUser.objects.filter(username=username).exclude(pk=user.pk).exists():
            user.username = username
        elif not user.username: # If user.username is blank and preferred_username is taken or not available
             # Attempt to generate a unique username if the primary one isn't available or set
            if email and not CustomUser.objects.filter(username=email).exclude(pk=user.pk).exists():
                user.username = email

        user.first_name = claims.get("given_name", user.first_name or "")
        user.last_name = claims.get("family_name", user.last_name or "")

        # Potentially set other fields if needed based on claims
        # e.g., user.is_active = True (though default adapter might handle this)

        return user

    def new_user(self, request, sociallogin):
        """
        Instantiates a new User instance.
        """
        user = super().new_user(request, sociallogin)
        # The populate_user method will be called after this to fill in details
        # from claims. If there's any pre-population logic needed before that,
        # it can go here. For example, setting is_active=True is common.
        user.is_active = True
        return user

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a
        social provider, but before the login is actually processed
        (and before any messages are sent).
        """
        # Example: check if email is verified by the provider
        # if sociallogin.account.provider == 'openid_connect':
        #     email_verified = sociallogin.account.extra_data.get('email_verified')
        #     if not email_verified:
        #         # Or handle as needed, e.g., by raising ImmediateHttpResponse
        #         # to redirect to a page explaining email verification is needed.
        #         pass
        pass

    # You might also need to override other methods like `validate_disconnect`
    # or `is_auto_signup_allowed` depending on project requirements.

    def get_email_address(self, request, sociallogin):
        """
        Ensures that the email from the OIDC provider is used.
        """
        email = sociallogin.account.extra_data.get('email')
        return email

    def get_login_redirect_url(self, request):
        # After social login, redirect to the frontend.
        # The frontend will then pick up the session and fetch user details.
        # This assumes the frontend has a default route like '/' or '/dashboard' for authenticated users.
        # You might want to make this configurable.
        # This is called if no other redirect is specified (e.g. by `process='connect'`)
        # For headless, the API will typically return user data directly or an MFA challenge,
        # so this redirect might be less relevant for pure API flows but good for the OAuth dance.

        # For headless, the client should ideally handle redirects based on API response.
        # However, during the OAuth dance, the browser is redirected back to an allauth URL
        # which then might call this. Pointing to a known frontend URL is safest.
        frontend_url = self.get_setting("HEADLESS_FRONTEND_URLS", {}).get("socialaccount_login_success", "/")
        if frontend_url == "/": # Default if not specifically set
            frontend_url = env("FRONTEND_URL", default="http://localhost:5173") + "/"
        return frontend_url

    def get_connect_redirect_url(self, request, socialaccount):
        # Similar to get_login_redirect_url, but for connecting accounts.
        frontend_url = self.get_setting("HEADLESS_FRONTEND_URLS", {}).get("socialaccount_connect_success", "/")
        if frontend_url == "/":
            frontend_url = env("FRONTEND_URL", default="http://localhost:5173") + "/"
        return frontend_url

    def get_signup_redirect_url(self, request):
        # After social signup, redirect to frontend.
        frontend_url = self.get_setting("HEADLESS_FRONTEND_URLS", {}).get("socialaccount_signup_success", "/")
        if frontend_url == "/":
            frontend_url = env("FRONTEND_URL", default="http://localhost:5173") + "/"
        return frontend_url
