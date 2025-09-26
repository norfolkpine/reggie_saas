# Notes and Code for Ephemeral File Handling

## Ephemeral File Uploads
- **No ingestion or indexing** is needed — just temporary context for a message.
- Keeps your database and vector store clean.
- You’re leveraging `agno.agent.Agent.run(..., files=[...])` which directly supports this flow.

### Backend

#### StreamAgentRequestSerializer
```python
from rest_framework import serializers
from agno.media import File  # Ensure you have this in your backend requirements

class StreamAgentRequestSerializer(serializers.Serializer):
    agent_name = serializers.CharField()
    message = serializers.CharField()
    session_id = serializers.CharField()
    files = serializers.ListField(
        child=serializers.FileField(), required=False
    )
```

#### stream_agent_response View
```python
from agno.media import File
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

MAX_FILE_SIZE_MB = 5  # Maximum file size in megabytes
MAX_FILES_COUNT = 5   # Maximum number of files

@api_view(['POST'])
def stream_agent_response(request):
    serializer = StreamAgentRequestSerializer(data=request.data)
    if serializer.is_valid():
        agent_name = serializer.validated_data['agent_name']
        message = serializer.validated_data['message']
        session_id = serializer.validated_data['session_id']
        files = request.FILES.getlist("files")

        # Check total number of files
        if len(files) > MAX_FILES_COUNT:
            return Response({'error': f'Maximum {MAX_FILES_COUNT} files are allowed.'}, status=status.HTTP_400_BAD_REQUEST)

        file_objs = []
        for f in files:
            # Check file size
            if f.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                return Response({'error': f'File {f.name} exceeds the size limit of {MAX_FILE_SIZE_MB} MB.'}, status=status.HTTP_400_BAD_REQUEST)

            file_obj = File(content=f.read(), mime_type=f.content_type)
            file_objs.append(file_obj)

        try:
            response_chunks = agent.run(message, stream=True, files=file_objs)
            return Response(response_chunks, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
```

### React Component
- Ensure files are included in the form submission to the backend.
- Update `handleSubmit` to send the files along with the message to the backend.
