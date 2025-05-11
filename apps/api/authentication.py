from rest_framework_api_key.authentication import APIKeyAuthentication
from rest_framework.exceptions import PermissionDenied


class CustomAPIKeyAuthentication(APIKeyAuthentication):
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except Exception:
            raise PermissionDenied("Invalid or missing API key") 