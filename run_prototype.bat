@echo off
title Outlook-to-ClickHouse Ingestion Platform Launcher
echo ============================================================
echo Starting Ingestion Platform Prototype Stack...
echo ============================================================

REM Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in your PATH. Please install Python 3.10+.
    pause
    exit /b 1
)

REM Check Node
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js was not found in your PATH. Please install Node.js.
    pause
    exit /b 1
)

echo.
echo [1/3] Setting up Backend Python virtual environment...
cd backend
if not exist "venv" (
    echo Creating python virtual environment...
    python -m venv venv
)
echo Activating virtual environment...
call venv\Scripts\activate
echo Installing backend python requirements...
pip install -r requirements.txt

echo.
echo [2/3] Launching FastAPI Backend Server (Port 8000)...
start "Backend Server (FastAPI)" cmd /c "call venv\Scripts\activate && python run.py"

cd ..

echo.
echo [3/3] Launching React/Vite Frontend Server (Port 5173)...
cd frontend
echo Running npm install...
call npm.cmd install
echo Starting Vite dev server...
echo.
echo Dashboard will load at http://localhost:5173
echo.
call npm.cmd run dev

pause
