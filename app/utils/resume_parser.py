import io
import re

from docx import Document
from pypdf import PdfReader


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError("Unable to read PDF file.") from exc

    text_chunks = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_chunks.append(page_text)

    raw_text = "\n".join(text_chunks)
    cleaned_text = _clean_text(raw_text)

    if not cleaned_text.strip():
        raise ValueError("PDF contains no extractable text.")

    return cleaned_text


def extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        document = Document(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError("Unable to read DOCX file.") from exc

    text_chunks = [paragraph.text for paragraph in document.paragraphs]
    raw_text = "\n".join(text_chunks)
    cleaned_text = _clean_text(raw_text)

    if not cleaned_text.strip():
        raise ValueError("DOCX contains no extractable text.")

    return cleaned_text


def _clean_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)

