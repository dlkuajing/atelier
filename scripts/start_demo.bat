@echo off
setlocal

cd /d "%~dp0"
cd /d ".."

if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8000"
if not defined PYTHONUTF8 set "PYTHONUTF8=1"

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo Starting Atelier demo at http://%HOST%:%PORT%
"%PYTHON_EXE%" -m uvicorn app.main:app --host "%HOST%" --port "%PORT%"
