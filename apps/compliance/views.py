from rest_framework import viewsets
from .models import Person, Document, ActionLog
from .serializers import PersonSerializer, DocumentSerializer, ActionLogSerializer

class PersonViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Persons to be viewed or edited.
    """
    queryset = Person.objects.all().order_by('-created_at')
    serializer_class = PersonSerializer

class DocumentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Documents to be viewed or edited.
    """
    queryset = Document.objects.all().order_by('-uploaded_at')
    serializer_class = DocumentSerializer

class ActionLogViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Action Logs to be viewed.
    """
    queryset = ActionLog.objects.all().order_by('-timestamp')
    serializer_class = ActionLogSerializer
    http_method_names = ['get', 'post', 'head', 'options'] # Logs are immutable once created
