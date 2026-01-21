import json
import os
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi.testclient import TestClient

import main


def build_sample_pdf_bytes() -> bytes:
    lines = [
        "BT",
        "/F1 18 Tf",
        "72 720 Td",
        "(Taylor Quinn - Backend Engineer) Tj",
        "0 -24 Td",
        "(Project: Inventory Optimization System) Tj",
        "0 -24 Td",
        "(Skills: Python, FastAPI, PostgreSQL) Tj",
        "ET",
        "",
    ]
    stream = "\n".join(lines)
    stream_bytes = stream.encode("utf-8")

    objects: List[bytes] = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
    )
    objects.append(
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n{stream}endstream\nendobj\n".encode(
            "utf-8"
        )
    )
    objects.append(
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )

    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_start = len(pdf)
    pdf.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))

    trailer = "trailer\n<< /Size 6 /Root 1 0 R >>\n"
    pdf.extend(trailer.encode("utf-8"))
    pdf.extend(f"startxref\n{xref_start}\n%%EOF\n".encode("utf-8"))
    return bytes(pdf)


def print_env_checklist() -> bool:
    required = ["OPENAI_API_KEY"]
    optional = ["OPENAI_BASE_URL", "OPENAI_API_BASE"]

    print("Voice Readiness Checklist:")
    all_ok = True
    for key in required:
        value = os.getenv(key)
        ok = bool(value)
        all_ok = all_ok and ok
        status = "OK" if ok else "MISSING"
        print(f"- {key}: {status}")

    for key in optional:
        value = os.getenv(key)
        status = "SET" if value else "NOT SET"
        print(f"- {key}: {status}")

    return all_ok


def assert_condition(label: str, condition: bool, details: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    suffix = f" | {details}" if details else ""
    print(f"[{status}] {label}{suffix}")
    return condition


def validate_candidate_profile(data: Dict[str, Any]) -> bool:
    required_fields = [
        "full_name",
        "email",
        "experience_years",
        "technical_stack",
        "education",
        "key_achievements",
        "seniority_level",
    ]
    missing = [field for field in required_fields if field not in data]
    if missing:
        return assert_condition("CandidateProfile shape", False, f"Missing fields: {missing}")

    return assert_condition("CandidateProfile shape", True)


def greeting_is_relevant(message: str, profile: Dict[str, Any]) -> bool:
    candidates: List[str] = []
    if profile.get("full_name"):
        candidates.append(profile["full_name"])
    candidates.extend(profile.get("technical_stack", [])[:3])
    candidates.extend(profile.get("key_achievements", [])[:2])
    if not candidates:
        return False
    lower_message = message.lower()
    return any(token.lower() in lower_message for token in candidates)


def is_star_followup(message: str) -> bool:
    hints = [
        "situation",
        "task",
        "action",
        "result",
        "context",
        "impact",
    ]
    lower_message = message.lower()
    return any(hint in lower_message for hint in hints)


def run_smoke_test() -> int:
    load_dotenv()
    env_ok = print_env_checklist()
    if not env_ok:
        assert_condition("Environment variables loaded", False, "Set OPENAI_API_KEY in .env")
        return 1
    assert_condition("Environment variables loaded", True)

    client = TestClient(main.app)

    pdf_bytes = build_sample_pdf_bytes()
    upload_response = client.post(
        "/upload-resume",
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert_condition("Mock PDF upload", upload_response.status_code == 200, upload_response.text)
    if upload_response.status_code != 200:
        return 1

    profile = upload_response.json()
    if not validate_candidate_profile(profile):
        return 1

    start_response = client.post(
        "/start-interview",
        json={"candidate_profile": profile, "job_description": ""},
    )
    assert_condition("Start interview", start_response.status_code == 200, start_response.text)
    if start_response.status_code != 200:
        return 1

    start_payload = start_response.json()
    session_id = start_payload.get("session_id")
    greeting = start_payload.get("message", "")
    assert_condition("Session id created", bool(session_id))
    assert_condition(
        "Greeting relevant to resume",
        greeting_is_relevant(greeting, profile),
        greeting,
    )

    shallow_response = client.post(
        "/chat",
        json={"session_id": session_id, "user_text": "It was fine. I don't remember the details."},
    )
    assert_condition("Shallow answer sent", shallow_response.status_code == 200, shallow_response.text)
    if shallow_response.status_code != 200:
        return 1
    shallow_reply = shallow_response.json().get("message", "")
    assert_condition("STAR follow-up detected", is_star_followup(shallow_reply), shallow_reply)

    agent = main.sessions.get(session_id)
    if not agent:
        assert_condition("Session persistence", False, "Session not found in memory.")
        return 1
    baseline_difficulty = agent.difficulty_score

    high_quality_answer = (
        "In my last project, I redesigned a FastAPI service to handle 5x traffic by introducing "
        "async I/O, caching hot routes in Redis, and optimizing PostgreSQL indexes. I profiled "
        "slow queries, added pagination, and wrote load tests that cut P95 latency from 900ms to "
        "180ms while keeping error rates under 0.2%. I can walk through trade-offs and monitoring."
    )

    for _ in range(2):
        client.post(
            "/chat",
            json={"session_id": session_id, "user_text": high_quality_answer},
        )
        if agent.difficulty_score > baseline_difficulty:
            break

    assert_condition(
        "Difficulty score increased",
        agent.difficulty_score > baseline_difficulty,
        f"before={baseline_difficulty}, after={agent.difficulty_score}",
    )

    metrics_response = client.get(f"/session/metrics/{session_id}")
    assert_condition("Metrics endpoint", metrics_response.status_code == 200, metrics_response.text)
    if metrics_response.status_code != 200:
        return 1
    metrics = metrics_response.json()
    tech_ok = isinstance(metrics.get("average_technical_accuracy"), (int, float)) and metrics.get(
        "average_technical_accuracy"
    )
    comm_ok = isinstance(metrics.get("average_communication_clarity"), (int, float)) and metrics.get(
        "average_communication_clarity"
    )
    assert_condition("Technical accuracy non-zero", bool(tech_ok), str(metrics))
    assert_condition("Communication clarity non-zero", bool(comm_ok), str(metrics))

    report_response = client.get(f"/session/report/{session_id}")
    assert_condition("Final report endpoint", report_response.status_code == 200, report_response.text)
    if report_response.status_code != 200:
        return 1
    report = report_response.json()
    verdict_ok = report.get("overall_verdict") in {"Strong Hire", "Hire", "No Hire"}
    summary_ok = bool(report.get("key_strengths")) and bool(report.get("critical_gaps"))
    assert_condition("Verdict present", verdict_ok, str(report.get("overall_verdict")))
    assert_condition("Summary present", summary_ok)

    all_passed = all(
        result for result in [
            env_ok,
            upload_response.status_code == 200,
            validate_candidate_profile(profile),
            start_response.status_code == 200,
            bool(session_id),
            greeting_is_relevant(greeting, profile),
            shallow_response.status_code == 200,
            is_star_followup(shallow_reply),
            agent.difficulty_score > baseline_difficulty,
            metrics_response.status_code == 200,
            bool(tech_ok),
            bool(comm_ok),
            report_response.status_code == 200,
            verdict_ok,
            summary_ok,
        ]
    )
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = run_smoke_test()
    if exit_code == 0:
        print("\nSmoke test completed successfully.")
    else:
        print("\nSmoke test failed. Review the FAIL items above.")
    sys.exit(exit_code)
