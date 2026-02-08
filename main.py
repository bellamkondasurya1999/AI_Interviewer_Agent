import argparse
import os
import threading
import time
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional, Union, Any

from dotenv import load_dotenv
from firebase_admin import firestore as firebase_firestore

from app.schema.candidate import CandidateProfile
from app.services.interviewer import InterviewAgent
from app.services.processor import analyze_resume
from app.services.firebase import get_firestore_client, verify_id_token, ensure_user_document
from app.services.storage import upload_resume_file
from app.utils.resume_parser import extract_text_from_pdf, extract_text_from_docx

load_dotenv()

app = FastAPI(
    title="AI Interview Agent API",
    description="API for AI-powered interview agent",
    version="1.0.0"
)

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

# In-memory interview sessions (session_id -> InterviewAgent)
sessions: Dict[str, InterviewAgent] = {}
session_meta: Dict[str, Dict[str, Optional[str]]] = {}

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"message": "AI Interview Agent API"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "AI Interview Agent API"
    }


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_id_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc

    user_id = claims.get("uid")
    email = claims.get("email")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload.")
    ensure_user_document(user_id, email)
    return {"user_id": user_id, "email": email}


@app.post("/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Upload resume endpoint - accepts PDF or DOCX files
    """
    filename_lower = file.filename.lower()
    if not (
        filename_lower.endswith(".pdf")
        or filename_lower.endswith(".docx")
        or filename_lower.endswith(".txt")
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF, DOCX, or TXT files are supported."
        )

    file_bytes = await file.read()

    try:
        if filename_lower.endswith(".pdf"):
            resume_text = extract_text_from_pdf(file_bytes)
        elif filename_lower.endswith(".docx"):
            resume_text = extract_text_from_docx(file_bytes)
        else:
            resume_text = file_bytes.decode("utf-8", errors="ignore")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profile = analyze_resume(resume_text)
    storage_path = upload_resume_file(
        user_id=user["user_id"],
        filename=file.filename or "resume",
        content_type=file.content_type,
        file_bytes=file_bytes,
    )

    db = get_firestore_client()
    doc_ref = db.collection("resumes").document()
    doc_ref.set(
        {
            "user_id": user["user_id"],
            "storage_path": storage_path,
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": len(file_bytes),
            "extracted_text": resume_text,
            "profile_json": profile.model_dump(),
            "created_at": firebase_firestore.SERVER_TIMESTAMP,
        }
    )
    return {"resume_id": doc_ref.id, "profile": profile}


class ChatRequest(BaseModel):
    session_id: str
    user_text: str


class StartInterviewRequest(BaseModel):
    candidate_profile: Optional[CandidateProfile] = None
    job_description: Optional[str] = None
    resume_id: Optional[str] = None


class FinalizeRequest(BaseModel):
    session_id: str


@app.post("/start-interview")
async def start_interview(
    request: Union[StartInterviewRequest, CandidateProfile],
    user: Dict[str, Any] = Depends(get_current_user),
):
    session_id = str(uuid4())
    job_description = ""
    resume_id: Optional[str] = None

    if isinstance(request, CandidateProfile):
        candidate_profile = request
    else:
        job_description = request.job_description or ""
        resume_id = request.resume_id
        candidate_profile = request.candidate_profile
        if resume_id:
            db = get_firestore_client()
            resume_doc = db.collection("resumes").document(resume_id).get()
            if not resume_doc.exists:
                raise HTTPException(status_code=404, detail="Resume not found.")
            resume_data = resume_doc.to_dict() or {}
            if resume_data.get("user_id") != user["user_id"]:
                raise HTTPException(status_code=403, detail="Resume access denied.")
            profile_json = resume_data.get("profile_json")
            if not profile_json:
                raise HTTPException(status_code=400, detail="Resume profile is missing.")
            candidate_profile = CandidateProfile(**profile_json)

    if candidate_profile is None:
        raise HTTPException(status_code=400, detail="Candidate profile is required.")

    agent = InterviewAgent(candidate_profile, job_description=job_description)
    sessions[session_id] = agent
    session_meta[session_id] = {"user_id": user["user_id"], "resume_id": resume_id}

    db = get_firestore_client()
    db.collection("interview_sessions").document(session_id).set(
        {
            "user_id": user["user_id"],
            "resume_id": resume_id,
            "job_description": job_description,
            "started_at": firebase_firestore.SERVER_TIMESTAMP,
        }
    )

    opening_message = agent.get_next_response(user_input=None)
    return {"session_id": session_id, "message": opening_message}


@app.post("/chat")
async def chat(request: ChatRequest, user: Dict[str, Any] = Depends(get_current_user)):
    agent = sessions.get(request.session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")
    meta = session_meta.get(request.session_id) or {}
    if meta.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Session access denied.")

    response = agent.get_next_response(request.user_text)
    return {"session_id": request.session_id, "message": response}


@app.get("/session/metrics/{session_id}")
async def session_metrics(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    agent = sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")
    meta = session_meta.get(session_id) or {}
    if meta.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Session access denied.")

    evaluations = agent.turn_evaluations
    if not evaluations:
        return {
            "session_id": session_id,
            "average_technical_accuracy": 0,
            "average_communication_clarity": 0,
            "average_confidence_score": 0,
            "average_confidence_label": "Low",
        }

    avg_tech = sum(ev.technical_accuracy for ev in evaluations) / len(evaluations)
    avg_comm = sum(ev.communication_clarity for ev in evaluations) / len(evaluations)
    confidence_map = {"Low": 1, "Med": 2, "High": 3}
    avg_confidence = sum(confidence_map[ev.confidence_signal] for ev in evaluations) / len(evaluations)
    if avg_confidence > 2.5:
        confidence_label = "High"
    elif avg_confidence >= 1.5:
        confidence_label = "Med"
    else:
        confidence_label = "Low"

    return {
        "session_id": session_id,
        "average_technical_accuracy": round(avg_tech, 2),
        "average_communication_clarity": round(avg_comm, 2),
        "average_confidence_score": round(avg_confidence, 2),
        "average_confidence_label": confidence_label,
    }


@app.post("/finalize")
async def finalize_interview(request: FinalizeRequest, user: Dict[str, Any] = Depends(get_current_user)):
    agent = sessions.get(request.session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")
    meta = session_meta.get(request.session_id) or {}
    if meta.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Session access denied.")

    report = agent.generate_final_report()
    db = get_firestore_client()
    db.collection("interview_sessions").document(request.session_id).set(
        {
            "ended_at": firebase_firestore.SERVER_TIMESTAMP,
            "final_report": report.model_dump(),
        },
        merge=True,
    )
    return {
        "session_id": request.session_id,
        "strengths": report.strengths,
        "areas_for_improvement": report.areas_for_improvement,
    }


@app.get("/session/report/{session_id}")
async def session_report(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    agent = sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")
    meta = session_meta.get(session_id) or {}
    if meta.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Session access denied.")

    report = agent.finalize_interview()
    db = get_firestore_client()
    db.collection("interview_sessions").document(session_id).set(
        {
            "ended_at": firebase_firestore.SERVER_TIMESTAMP,
            "summary_report": report.model_dump(),
        },
        merge=True,
    )
    return {
        "session_id": session_id,
        "overall_verdict": report.overall_verdict,
        "key_strengths": report.key_strengths,
        "critical_gaps": report.critical_gaps,
        "culture_fit_score": report.culture_fit_score,
    }


if __name__ == "__main__":
    def run_server() -> None:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8000)

    def _start_test_server(host: str, port: int):
        import uvicorn

        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(50):
            if server.started:
                break
            time.sleep(0.1)
        return server, thread

    def run_all() -> int:
        print("Running all project checks...\n")
        root_dir = os.path.dirname(__file__)
        ran_any = False
        exit_code = 0

        if os.path.isfile(os.path.join(root_dir, "verify_system.py")):
            ran_any = True
            try:
                from verify_system import run_smoke_test

                smoke_code = run_smoke_test()
                exit_code = max(exit_code, smoke_code)
            except Exception as exc:
                print(f"Smoke test failed: {exc}")
                exit_code = 1
        else:
            print("Skipping smoke test: verify_system.py not found.")

        if os.path.isfile(os.path.join(root_dir, "test_day1.py")):
            ran_any = True
            host = "127.0.0.1"
            port = 8001
            os.environ["API_BASE_URL"] = f"http://{host}:{port}"
            server, thread = _start_test_server(host, port)
            if not server.started:
                print("Failed to start local API server for test_day1.")
                return 1

            try:
                from test_day1 import main as test_day1_main

                test_code = test_day1_main()
                exit_code = max(exit_code, test_code)
            except Exception as exc:
                print(f"test_day1 failed: {exc}")
                exit_code = 1
            finally:
                server.should_exit = True
                thread.join(timeout=5)
        else:
            print("Skipping test_day1: test_day1.py not found.")

        if not ran_any:
            print("No local checks found. Starting API server instead.\n")
            run_server()
            return 0

        return exit_code

    parser = argparse.ArgumentParser(description="AI Interview Agent runner")
    parser.add_argument("--serve", action="store_true", help="Run the API server only")
    parser.add_argument("--run-all", action="store_true", help="Run all local checks and demos")
    args = parser.parse_args()

    if args.serve:
        run_server()
    else:
        raise SystemExit(run_all())