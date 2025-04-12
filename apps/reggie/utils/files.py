import os
from datetime import datetime

def user_document_path(instance, filename):
    user_id = instance.uploaded_by.id if instance.uploaded_by else "anonymous"
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    base, ext = os.path.splitext(filename)
    return f"users/{user_id}/uploads/{base}-{timestamp}{ext}"