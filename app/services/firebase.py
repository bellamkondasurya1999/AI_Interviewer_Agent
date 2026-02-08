import os
from typing import Optional, Dict, Any

import firebase_admin
from firebase_admin import credentials, firestore, storage, auth
from google.cloud.storage import Bucket

_app: Optional[firebase_admin.App] = None


def _normalize_private_key(raw_key: str) -> str:
    if not raw_key:
        return ""
    if "\\n" in raw_key:
        return raw_key.replace("\\n", "\n")
    return raw_key


def initialize_firebase() -> firebase_admin.App:
    global _app
    if _app is not None:
        return _app

    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL", "").strip()
    private_key = _normalize_private_key(os.getenv("FIREBASE_PRIVATE_KEY", "").strip())
    storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()

    if not project_id or not client_email or not private_key or not storage_bucket:
        raise RuntimeError(
            "Missing Firebase config. Set FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, "
            "FIREBASE_PRIVATE_KEY, and FIREBASE_STORAGE_BUCKET."
        )

    cred = credentials.Certificate(
        {
            "type": "service_account",
            "project_id": project_id,
            "client_email": client_email,
            "private_key": private_key,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    _app = firebase_admin.initialize_app(
        cred,
        {"storageBucket": storage_bucket, "projectId": project_id},
    )
    return _app


def get_firestore_client() -> firestore.Client:
    initialize_firebase()
    return firestore.client()


def get_storage_bucket() -> Bucket:
    initialize_firebase()
    return storage.bucket()


def verify_id_token(token: str) -> Dict[str, Any]:
    initialize_firebase()
    return auth.verify_id_token(token)


def ensure_user_document(user_id: str, email: Optional[str]) -> None:
    db = get_firestore_client()
    doc_ref = db.collection("users").document(user_id)
    doc_ref.set(
        {
            "email": email,
            "created_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
