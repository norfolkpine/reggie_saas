from dj_rest_auth.serializers import JWTSerializer
from rest_framework import serializers
from dj_rest_auth.registration.serializers import RegisterSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    detail = serializers.CharField()
    jwt = JWTSerializer(required=False)
    temp_otp_token = serializers.CharField(required=False)


class OtpRequestSerializer(serializers.Serializer):
    temp_otp_token = serializers.CharField()
    otp = serializers.CharField()


class CustomRegisterSerializer(RegisterSerializer):
    def validate_email(self, email):
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_username(self, username):
        if username and User.objects.filter(username=username).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return username
