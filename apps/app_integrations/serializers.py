from rest_framework import serializers

from .models import NangoIntegration, SupportedApp


class SupportedAppSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportedApp
        fields = ["id", "key", "title", "description", "icon_url", "is_enabled"]


class GoogleOAuthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    message = serializers.CharField(read_only=True)


class GoogleOAuthStartResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField()


class GoogleDriveRevokeRequestSerializer(serializers.Serializer):
    pass  # No request body needed


class GoogleDriveRevokeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    error = serializers.CharField(required=False)


class GoogleDriveDownloadResponseSerializer(serializers.Serializer):
    content = serializers.FileField()
    content_type = serializers.CharField()


class GoogleDriveFileSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    mimeType = serializers.CharField()
    createdTime = serializers.DateTimeField(required=False)
    modifiedTime = serializers.DateTimeField(required=False)
    size = serializers.IntegerField(required=False)
    iconLink = serializers.URLField(required=False)
    webViewLink = serializers.URLField(required=False)


class GoogleDriveListResponseSerializer(serializers.Serializer):
    files = GoogleDriveFileSerializer(many=True)
    nextPageToken = serializers.CharField(required=False)


class GoogleDriveUploadResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    mimeType = serializers.CharField()


class GoogleDocFromMarkdownRequestSerializer(serializers.Serializer):
    markdown = serializers.CharField()
    title = serializers.CharField(required=False, default="Untitled AI Output")


class GoogleDocFromMarkdownResponseSerializer(serializers.Serializer):
    file_id = serializers.CharField()
    doc_url = serializers.URLField()
    title = serializers.CharField()


class NangoIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = NangoIntegration
        fields = ["id", "user_id", "connection_id", "provider"]
