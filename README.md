# AI Interview Agent

A FastAPI-based backend for an AI-powered interview agent system.

## Project Structure

```
.
├── app/
│   ├── agents/          # AI agent implementations
│   ├── utils/           # Utility functions
│   └── schema/          # Pydantic models and schemas
├── main.py              # FastAPI application entry point
├── requirements.txt     # Python dependencies
└── .env                 # Environment variables

```

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
- Windows: `venv\Scripts\activate`
- Linux/Mac: `source venv/bin/activate`

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
   - Open `.env` in the project root
   - Set `OPENAI_API_KEY=your_openai_api_key_here`
   - Remove `OPENAI_BASE_URL` / `OPENAI_API_BASE` if present (OpenAI only)

## Running the Application

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## Solution Narrative

**Alex — Hands-Free AI Technical Interviewer**

**Problem:** Most interview prep tools feel scripted and repetitive. They fail to adapt to a
candidate's resume and live responses.

**Solution:** Alex is a conversational technical interviewer that uses full session memory to
avoid repetition and dynamically deep-dive into technologies a candidate mentions. The system
is hands-free: it listens, waits for silence, responds, and resumes listening automatically.

**How it works:**
- Resume upload is parsed into a structured candidate profile.
- Each interview session stores all messages; the model sees the full history every turn.
- Alex acknowledges the last answer and asks a focused follow-up based on that content.
- The frontend uses voice input and speech synthesis to create a natural dialogue loop.
- The UI provides real-time visual feedback via a responsive Voice Orb.

**Why it scores well:**
- Memory-aware: avoids repeated prompts
- Adaptive: pivots into deep technical areas (e.g., Time Series, LightGBM)
- Hands-free: auto listen/response cycle
- Polished UI: voice visualization and clean layout

## Demo Video

Add your demo link here:
- https://youtu.be/REPLACE_WITH_DEMO

## Repository

- https://github.com/bellamkondasurya1999/AI_Interviewer_Agent

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check endpoint
- `POST /upload-resume` - Upload resume (PDF or Word document)

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

