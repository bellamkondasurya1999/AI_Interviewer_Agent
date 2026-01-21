import os

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional, Union

from dotenv import load_dotenv

from app.schema.candidate import CandidateProfile
from app.services.interviewer import InterviewAgent
from app.services.processor import analyze_resume
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


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
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
    return profile


class ChatRequest(BaseModel):
    session_id: str
    user_text: str


class StartInterviewRequest(BaseModel):
    candidate_profile: CandidateProfile
    job_description: Optional[str] = None


class FinalizeRequest(BaseModel):
    session_id: str


@app.post("/start-interview")
async def start_interview(request: Union[StartInterviewRequest, CandidateProfile]):
    session_id = str(len(sessions) + 1)
    if isinstance(request, CandidateProfile):
        candidate_profile = request
        job_description = ""
    else:
        candidate_profile = request.candidate_profile
        job_description = request.job_description or ""

    agent = InterviewAgent(candidate_profile, job_description=job_description)
    sessions[session_id] = agent

    opening_message = agent.get_next_response(user_input=None)
    return {"session_id": session_id, "message": opening_message}


@app.post("/chat")
async def chat(request: ChatRequest):
    agent = sessions.get(request.session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")

    response = agent.get_next_response(request.user_text)
    return {"session_id": request.session_id, "message": response}


@app.get("/session/metrics/{session_id}")
async def session_metrics(session_id: str):
    agent = sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")

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
async def finalize_interview(request: FinalizeRequest):
    agent = sessions.get(request.session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")

    report = agent.generate_final_report()
    return {
        "session_id": request.session_id,
        "strengths": report.strengths,
        "areas_for_improvement": report.areas_for_improvement,
    }


@app.get("/session/report/{session_id}")
async def session_report(session_id: str):
    agent = sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found.")

    report = agent.finalize_interview()
    return {
        "session_id": session_id,
        "overall_verdict": report.overall_verdict,
        "key_strengths": report.key_strengths,
        "critical_gaps": report.critical_gaps,
        "culture_fit_score": report.culture_fit_score,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

