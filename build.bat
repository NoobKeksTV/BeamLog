@echo off
rem Portable Windows-Version bauen (Ergebnis in dist\)
cd /d "%~dp0"
if not exist .venv (python -m venv .venv && .venv\Scripts\python -m pip install -q -r requirements.txt)
.venv\Scripts\python -m pip install -q pyinstaller
.venv\Scripts\python build_tools\build.py %*
pause
