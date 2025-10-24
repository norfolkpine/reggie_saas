from rest_framework import serializers
from .models import Person, Document, ActionLog

class PersonSerializer(serializers.ModelSerializer):
    """
    Serializer for the Person model.
    """
    class Meta:
        model = Person
        fields = '__all__'

class DocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for the Document model.
    """
    class Meta:
        model = Document
        fields = '__all__'

class ActionLogSerializer(serializers.ModelSerializer):
    """
    Serializer for the ActionLog model.
    """
    class Meta:
        model = ActionLog
        fields = '__all__'
