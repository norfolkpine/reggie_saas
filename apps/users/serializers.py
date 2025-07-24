from rest_framework import serializers

from .models import CustomUser


class CustomUserSerializer(serializers.ModelSerializer):
    is_superuser = serializers.BooleanField(read_only=True)
    """
    Basic serializer to pass CustomUser details to the front end.
    Extend with any fields your app needs.
    """

    class Meta:
        model = CustomUser
        fields = ("id", "first_name", "last_name", "email", "avatar_url", "get_display_name", "is_superuser")
