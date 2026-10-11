@echo off
rem BeamLog starten (Windows). Legt beim ersten Mal die virtuelle Umgebung .venv an und
rem installiert die Pakete neu, sobald sich requirements.txt geaendert hat (z. B. nach git pull).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Erster Start: richte .venv ein ...
  python -m venv .venv || (echo Python 3 wird benoetigt: https://www.python.org/downloads/ & pause & exit /b 1)
)
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo Installiere Python-Pakete ...
  .venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)
  copy /y requirements.txt .venv\requirements.installed >nul
)
.venv\Scripts\python run.py %*
pause
