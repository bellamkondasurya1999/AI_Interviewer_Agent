import json
import os
import sys
import uuid
from typing import Dict, Tuple
from urllib import request, error

from dotenv import load_dotenv


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def build_pdf_bytes(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 24 Tf 50 150 Td ({escaped}) Tj ET"
    stream_bytes = stream.encode("utf-8")
    length = len(stream_bytes)

    header = "%PDF-1.4\n"
    objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        (
            f"4 0 obj\n<< /Length {length} >>\nstream\n{stream}\n"
            "endstream\nendobj\n"
        ),
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    offsets = []
    current_offset = len(header.encode("utf-8"))
    for obj in objects:
        offsets.append(current_offset)
        current_offset += len(obj.encode("utf-8"))

    xref_start = current_offset
    xref_lines = ["xref", "0 6", "0000000000 65535 f "]
    for offset in offsets:
        xref_lines.append(f"{offset:010d} 00000 n ")
    xref = "\n".join(xref_lines) + "\n"

    trailer = (
        "trailer\n<< /Size 6 /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    )

    pdf = header + "".join(objects) + xref + trailer
    return pdf.encode("utf-8")


def build_multipart(field_name: str, filename: str, content_type: str, data: bytes) -> Tuple[bytes, str]:
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = b"\r\n".join(
        [
            f"--{boundary}".encode("utf-8"),
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode("utf-8"),
            f"Content-Type: {content_type}".encode("utf-8"),
            b"",
            data,
            f"--{boundary}--".encode("utf-8"),
            b"",
        ]
    )
    return body, boundary


def http_post(url: str, body: bytes, headers: Dict[str, str]) -> Tuple[int, str]:
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8")
    except error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def main() -> int:
    load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("FAIL ENV CHECK: OPENAI_API_KEY not set in .env")
        return 1
    print("OK ENV CHECK: OPENAI_API_KEY is set")

    pdf_bytes = build_pdf_bytes("Test User resume for AI Interview Agent.")
    body, boundary = build_multipart(
        field_name="file",
        filename="sample.pdf",
        content_type="application/pdf",
        data=pdf_bytes,
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    try:
        upload_status, upload_resp = http_post(f"{BASE_URL}/upload-resume", body, headers)
    except error.URLError as exc:
        print(f"FAIL UPLOAD: Failed to connect to server at {BASE_URL}: {exc}")
        return 1

    if upload_status != 200:
        print(f"FAIL UPLOAD: HTTP {upload_status}")
        print(upload_resp)
        return 1

    try:
        profile = json.loads(upload_resp)
    except json.JSONDecodeError:
        print("FAIL UPLOAD: Response is not valid JSON")
        print(upload_resp)
        return 1

    required_fields = {"full_name", "seniority_level"}
    if not required_fields.issubset(profile.keys()):
        print("FAIL VALIDATE: Missing expected fields in profile JSON")
        print(profile)
        return 1
    print("OK UPLOAD: Resume processed and profile returned")

    start_body = json.dumps(profile).encode("utf-8")
    start_headers = {"Content-Type": "application/json"}
    start_status, start_resp = http_post(f"{BASE_URL}/start-interview", start_body, start_headers)
    if start_status != 200:
        print(f"FAIL START: HTTP {start_status}")
        print(start_resp)
        return 1
    start_data = json.loads(start_resp)
    session_id = start_data.get("session_id")
    first_message = start_data.get("message")
    if not session_id or not first_message:
        print("FAIL START: Missing session_id or message")
        print(start_data)
        return 1
    print("OK START: Interview session created")

    chat_payload = json.dumps(
        {"session_id": session_id, "user_text": "Thanks! Excited to chat."}
    ).encode("utf-8")
    chat_status, chat_resp = http_post(f"{BASE_URL}/chat", chat_payload, start_headers)
    if chat_status != 200:
        print(f"FAIL CHAT: HTTP {chat_status}")
        print(chat_resp)
        return 1
    chat_data = json.loads(chat_resp)
    second_message = chat_data.get("message")
    if not second_message:
        print("FAIL CHAT: Missing response message")
        print(chat_data)
        return 1
    print("OK CHAT: Follow-up message received")

    print("\n--- AI RESPONSES ---")
    print("1)", first_message)
    print("2)", second_message)
    return 0


if __name__ == "__main__":
    sys.exit(main())

