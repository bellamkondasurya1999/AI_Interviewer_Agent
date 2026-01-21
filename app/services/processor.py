import json
import os
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.schema.candidate import CandidateProfile


SYSTEM_PROMPT = (
    "You are a Senior Technical Recruiter. Your task is to extract professional "
    "details from the provided resume text into the requested JSON format. "
    "If information is missing, use your best judgment or mark as Unknown."
)


def analyze_resume(raw_text: str) -> CandidateProfile:
    if not raw_text.strip():
        raise ValueError("Resume text is empty.")

    os.environ.pop("OPENAI_BASE_URL", None)
    os.environ.pop("OPENAI_API_BASE", None)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=raw_text),
    ]

    if hasattr(llm, "with_structured_output"):
        structured_llm = llm.with_structured_output(CandidateProfile)
        return structured_llm.invoke(messages)

    fallback_messages = [
        SystemMessage(
            content=(
                f"{SYSTEM_PROMPT}\n\n"
                "Return ONLY a valid JSON object that matches this schema:\n"
                "{"
                "\"full_name\": \"string\", "
                "\"email\": \"string or null\", "
                "\"experience_years\": number, "
                "\"technical_stack\": [\"string\"], "
                "\"education\": [\"string\"], "
                "\"key_achievements\": [\"string\"], "
                "\"seniority_level\": \"Junior|Mid|Senior|Lead\""
                "}"
            )
        ),
        HumanMessage(content=raw_text),
    ]
    response = llm.invoke(fallback_messages)
    content = response.content or ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError("Model did not return valid JSON.") from exc
        else:
            raise ValueError("Model did not return valid JSON.")
    return CandidateProfile(**data)

