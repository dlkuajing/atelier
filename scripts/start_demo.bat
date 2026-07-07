@echo off
setlocal

cd /d "%~dp0"
cd /d ".."

if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8000"
if not defined PYTHONUTF8 set "PYTHONUTF8=1"

if not exist ".env" (
  echo Missing .env file.
  echo Create .env from .env.example and set OPENAI_API_KEY before starting the demo.
  exit /b 1
)

REM Pure-batch .env key check: sandboxed loop gates run with a stripped PATH
REM where powershell.exe is not resolvable, so no external tools here.
set "OPENAI_KEY_VALUE="
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  for /f "tokens=* delims= " %%K in ("%%A") do (
    if /i "%%K"=="OPENAI_API_KEY" set "OPENAI_KEY_VALUE=%%B"
  )
)
if defined OPENAI_KEY_VALUE set "OPENAI_KEY_VALUE=%OPENAI_KEY_VALUE:"=%"
if defined OPENAI_KEY_VALUE set "OPENAI_KEY_VALUE=%OPENAI_KEY_VALUE:'=%"
if defined OPENAI_KEY_VALUE (
  for /f "tokens=* delims= " %%V in ("%OPENAI_KEY_VALUE%") do set "OPENAI_KEY_VALUE=%%V"
)
if not defined OPENAI_KEY_VALUE (
  echo OPENAI_API_KEY is missing or empty in .env.
  echo Edit .env and set OPENAI_API_KEY before starting the demo.
  exit /b 1
)
set "OPENAI_KEY_VALUE="

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo Starting Atelier demo at http://%HOST%:%PORT%
"%PYTHON_EXE%" -m uvicorn app.main:app --host "%HOST%" --port "%PORT%"
