@echo off
rem ContestLogger starten (Windows). Legt beim ersten Mal eine virtuelle Umgebung an.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || (echo Python 3 wird benoetigt: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
.venv\Scripts\python run.py %*
pause
