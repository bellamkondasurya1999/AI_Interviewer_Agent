import os
import json
import anyio
import httpx
from app.schema.candidate import CandidateProfile
from app.services.interviewer import InterviewAgent
from main import app, sessions

key = os.getenv("OPENAI_API_KEY")
print("OPENAI_API_KEY set:", bool(key))
if not key:
    raise SystemExit("Missing OPENAI_API_KEY; cannot run live LLM tests.")

profile = CandidateProfile(
    full_name="Test User",
    email="test@example.com",
    experience_years=3,
    technical_stack=["Python", "FastAPI", "PostgreSQL"],
    education=["BS CS"],
    key_achievements=["Built an API"],
    seniority_level="Mid",
)

agent = InterviewAgent(profile, job_description="Kubernetes, AWS, System design")

print("\n--- Follow-up Test ---")
opening = agent.get_next_response(user_input=None)
print("Opening:", opening)
followup = agent.get_next_response("I used Python to fix bugs.")
print("AI Response:", followup)
print("Asked for specific example:", "impact" in followup.lower() or "result" in followup.lower() or "specifically" in followup.lower())

print("\n--- Difficulty Test ---")
ans1 = (
    "Situation: We had a monolith under heavy load. Task: reduce p95 latency. "
    "Action: I profiled hotspots, introduced async I/O, added Redis caching, and "
    "optimized SQL indexes. Result: p95 dropped from 900ms to 220ms and error rate fell 40%."
)
ans2 = (
    "Situation: Our event pipeline dropped messages. Task: improve reliability. "
    "Action: I added idempotent consumers, implemented at-least-once semantics, and "
    "added DLQs plus monitoring. Result: data loss went to ~0 and throughput increased 2x."
)
resp1 = agent.get_next_response(ans1)
print("After answer 1, difficulty_score:", agent.difficulty_score)
print("Next question:", resp1)
resp2 = agent.get_next_response(ans2)
print("After answer 2, difficulty_score:", agent.difficulty_score)
print("Next question:", resp2)

print("\n--- Metrics Test ---")
session_id = "manual"
sessions[session_id] = agent

async def fetch_metrics():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get(f"/session/metrics/{session_id}")
        return resp.status_code, resp.json()

status, data = anyio.run(fetch_metrics)
print("/session/metrics status:", status)
print(json.dumps(data, indent=2))
