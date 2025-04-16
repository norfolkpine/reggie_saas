import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.app_integrations.models import ConnectedApp, SupportedApp
from apps.app_integrations.utils.google_docs_markdown import parse_markdown_text, text_to_google_docs_requests


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@csrf_exempt
def create_google_doc_from_markdown(request):
    try:
        markdown = request.data.get("markdown")
        title = request.data.get("title", "Untitled AI Output")
        if not markdown:
            return JsonResponse({"error": "Missing markdown content."}, status=400)

        try:
            google_drive_app = SupportedApp.objects.get(key='google_drive')
        except SupportedApp.DoesNotExist:
            return JsonResponse({"error": "Google Drive integration is not configured in the system."}, status=404)
            
        try:
            creds = ConnectedApp.objects.get(user=request.user, app_id=google_drive_app.id)
            access_token = creds.get_valid_token()
        except ConnectedApp.DoesNotExist:
            return JsonResponse(
                {"error": "Google Drive is not connected for your account. Please connect Google Drive first."}, 
                status=401
            )
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        create_res = requests.post(
            "https://docs.googleapis.com/v1/documents",
            headers=headers,
            json={"title": title},
            timeout=10,
        )
        create_res.raise_for_status()
        doc_id = create_res.json()["documentId"]
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to create Google Doc", "details": str(e)}, status=502)

    try:
        plain_text, actions = parse_markdown_text(markdown)
        doc_requests = text_to_google_docs_requests(plain_text, actions)
        batch_body = {"requests": doc_requests}
    except Exception as e:
        return JsonResponse({"error": "Markdown conversion failed", "details": str(e)}, status=500)

    try:
        update_res = requests.post(
            f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
            headers=headers,
            json=batch_body,
            timeout=10,
        )
        update_res.raise_for_status()
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to insert content", "details": str(e)}, status=502)

    return JsonResponse(
        {
            "file_id": doc_id,
            "doc_url": f"https://docs.google.com/document/d/{doc_id}/edit",
            "title": title,
        }
    )
