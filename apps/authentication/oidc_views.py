from django.contrib.auth import login
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import View
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView
from rest_framework_simplejwt.tokens import RefreshToken
from allauth.mfa.totp.internal.auth import TOTP
from allauth.mfa.models import Authenticator

from .api_views import VerifyOTPView

class CustomOIDCAuthenticationCallbackView(OIDCAuthenticationCallbackView):
    """Custom OIDC callback view that handles 2FA."""
    
    def login_success(self):
        """Handle successful OIDC login."""
        user = self.user
        
        # Check if 2FA is required
        if hasattr(user, 'authenticator') and user.authenticator.type == Authenticator.Type.TOTP:
            # Store user ID in session for 2FA verification
            self.request.session['pending_oidc_user_id'] = user.id
            return redirect('authentication:verify_oidc_otp')
            
        # No 2FA required, proceed with normal login
        login(self.request, user)
        return redirect(self.get_success_url())

class OIDCVerifyOTPView(VerifyOTPView):
    """View to verify OTP for OIDC authentication."""
    
    def post(self, request):
        """Handle OTP verification for OIDC login."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        otp = serializer.validated_data['otp']
        user_id = request.session.get('pending_oidc_user_id')
        
        if not user_id:
            return Response(
                {'status': 'error', 'detail': 'No pending OIDC authentication'},
                status=400
            )
            
        user = self.get_user_model().objects.get(id=user_id)
        
        if TOTP(Authenticator.objects.get(user=user, type=Authenticator.Type.TOTP)).validate_code(otp):
            # OTP is valid, complete login
            login(request, user)
            del request.session['pending_oidc_user_id']
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            return Response({
                'status': 'success',
                'detail': 'OTP verified successfully',
                'jwt': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            })
            
        return Response(
            {'status': 'error', 'detail': 'Invalid OTP'},
            status=400
        ) 