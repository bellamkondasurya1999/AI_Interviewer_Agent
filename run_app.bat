@echo off
setlocal enabledelayedexpansion

set ROOT_DIR=%~dp0
set ENV_FILE=%ROOT_DIR%.env

if not exist "%ENV_FILE%" (
  echo [ERROR] .env file not found at project root.
  exit /b 1
)

findstr /B /C:"OPENAI_API_KEY=" "%ENV_FILE%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] OPENAI_API_KEY is missing in .env.
  exit /b 1
)

if not exist "%ROOT_DIR%venv\Scripts\activate.bat" (
  echo [ERROR] venv not found. Please create it with: python -m venv venv
  exit /b 1
)

echo Starting backend...
cd /d "%ROOT_DIR%"
call "%ROOT_DIR%venv\Scripts\activate.bat"
python -m pip install -r requirements.txt
start "Frontend" cmd /k "cd /d \"%ROOT_DIR%frontend\" && npm install && npm run dev"
start "Backend" cmd /k "cd /d \"%ROOT_DIR%\" && call \"%ROOT_DIR%venv\Scripts\activate.bat\" && uvicorn main:app --reload --port 8000"

echo System Live! Access Frontend at http://localhost:5173 and Backend Docs at http://localhost:8000/docs
endlocal
