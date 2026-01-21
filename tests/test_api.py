import anyio
import httpx

from app.services.evaluator import TurnEvaluation
from app.services.interviewer import InterviewAgent
from main import app, sessions

async def _post_json(path: str, payload):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(path, json=payload)
        return resp.status_code, resp.json()


async def _get(path: str):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(path)
        return resp.status_code, resp.json()


def _profile_payload():
    return {
        "full_name": "Test User",
        "email": "test@example.com",
        "experience_years": 3,
        "technical_stack": ["Python", "FastAPI"],
        "education": ["BS CS"],
        "key_achievements": ["Built an API"],
        "seniority_level": "Mid",
    }


def test_start_interview_wrapped_payload(monkeypatch):
    def stub_get_next_response(self, user_input=None):
        return "stubbed response"

    monkeypatch.setattr(InterviewAgent, "get_next_response", stub_get_next_response)
    sessions.clear()

    status, data = anyio.run(
        _post_json,
        "/start-interview",
        {
            "candidate_profile": _profile_payload(),
            "job_description": "Kubernetes, AWS, System design",
        },
    )
    assert status == 200
    assert data["session_id"]
    assert data["message"] == "stubbed response"


def test_start_interview_legacy_payload(monkeypatch):
    def stub_get_next_response(self, user_input=None):
        return "legacy response"

    monkeypatch.setattr(InterviewAgent, "get_next_response", stub_get_next_response)
    sessions.clear()

    status, data = anyio.run(_post_json, "/start-interview", _profile_payload())
    assert status == 200
    assert data["session_id"]
    assert data["message"] == "legacy response"


def test_session_metrics_average_scores(monkeypatch):
    def stub_get_next_response(self, user_input=None):
        return "hello"

    monkeypatch.setattr(InterviewAgent, "get_next_response", stub_get_next_response)
    sessions.clear()

    status, data = anyio.run(_post_json, "/start-interview", _profile_payload())
    session_id = data["session_id"]

    agent = sessions[session_id]
    agent.turn_evaluations = [
        TurnEvaluation(technical_accuracy=8, communication_clarity=7, confidence_signal="High"),
        TurnEvaluation(technical_accuracy=6, communication_clarity=5, confidence_signal="Med"),
    ]

    metrics_status, metrics = anyio.run(_get, f"/session/metrics/{session_id}")
    assert metrics_status == 200
    assert metrics["average_technical_accuracy"] == 7.0
    assert metrics["average_communication_clarity"] == 6.0
    assert metrics["average_confidence_label"] == "Med"
