from urllib.parse import urlencode

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP
from django.contrib import auth
from django.contrib.auth import login
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import crypto
from mozilla_django_oidc.utils import absolutify
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView
from mozilla_django_oidc.views import OIDCLogoutView as MozillaOIDCOIDCLogoutView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .api_views import VerifyOTPView


class CustomOIDCAuthenticationCallbackView(OIDCAuthenticationCallbackView):
    """Custom OIDC callback view that handles 2FA."""

    def login_success(self):
        user = self.user

        # If user requires TOTP 2FA
        if hasattr(user, "authenticator") and user.authenticator.type == Authenticator.Type.TOTP:
            self.request.session["pending_oidc_user_id"] = user.id
            return redirect("authentication:verify_oidc_otp")

        # Normal login flow
        login(self.request, user)
        return redirect(self.get_success_url())


class OIDCVerifyOTPView(VerifyOTPView):
    """OTP verification view for OIDC-based logins."""

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp = serializer.validated_data["otp"]
        user_id = request.session.get("pending_oidc_user_id")

        if not user_id:
            return Response({"status": "error", "detail": "No pending OIDC authentication"}, status=400)

        user = self.get_user_model().objects.get(id=user_id)
        auth_record = Authenticator.objects.get(user=user, type=Authenticator.Type.TOTP)

        if TOTP(auth_record).validate_code(otp):
            login(request, user)
            del request.session["pending_oidc_user_id"]

            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "status": "success",
                    "detail": "OTP verified successfully",
                    "jwt": {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    },
                }
            )

        return Response({"status": "error", "detail": "Invalid OTP"}, status=400)


class OIDCLogoutView(MozillaOIDCOIDCLogoutView):
    """Custom logout view for OpenID Connect."""

    @staticmethod
    def persist_state(request, state):
        """Save OIDC state in session."""
        if "oidc_states" not in request.session or not isinstance(request.session["oidc_states"], dict):
            request.session["oidc_states"] = {}
        request.session["oidc_states"][state] = {}
        request.session.save()

    def construct_oidc_logout_url(self, request):
        """Build OIDC logout redirect URL."""
        oidc_logout_endpoint = self.get_settings("OIDC_OP_LOGOUT_ENDPOINT")
        if not oidc_logout_endpoint:
            return self.redirect_url

        id_token = request.session.get("oidc_id_token")
        if not id_token:
            return self.redirect_url

        state = crypto.get_random_string(self.get_settings("OIDC_STATE_SIZE", 32))
        redirect_uri = absolutify(request, reverse("oidc_logout_callback"))
        self.persist_state(request, state)

        query = {
            "id_token_hint": id_token,
            "state": state,
            "post_logout_redirect_uri": redirect_uri,
        }

        return f"{oidc_logout_endpoint}?{urlencode(query)}"

    def post(self, request):
        """Handle logout post request."""
        logout_url = self.redirect_url
        if request.user.is_authenticated:
            logout_url = self.construct_oidc_logout_url(request)

        if logout_url == self.redirect_url:
            auth.logout(request)

        return HttpResponseRedirect(logout_url)


class OIDCLogoutCallbackView(MozillaOIDCOIDCLogoutView):
    """Handles callback after OIDC logout."""

    http_method_names = ["get"]

    def get(self, request):
        if not request.user.is_authenticated:
            return HttpResponseRedirect(self.redirect_url)

        state = request.GET.get("state")
        oidc_states = request.session.get("oidc_states", {})

        if state not in oidc_states:
            raise SuspiciousOperation("OIDC callback state not found in session `oidc_states`!")

        del request.session["oidc_states"][state]
        request.session.save()

        auth.logout(request)
        return HttpResponseRedirect(self.redirect_url)
