from typing import Optional
from uuid import uuid4

from app.services.firebase import get_storage_bucket


def upload_resume_file(
    user_id: str,
    filename: str,
    content_type: Optional[str],
    file_bytes: bytes,
) -> str:
    bucket = get_storage_bucket()
    object_name = f"resumes/{user_id}/{uuid4()}/{filename}"
    blob = bucket.blob(object_name)
    blob.upload_from_string(file_bytes, content_type=content_type or "application/octet-stream")
    return object_name
