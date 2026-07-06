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

set "HAS_OPENAI_API_KEY="
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
  if /i "%%A"=="OPENAI_API_KEY" if not "%%B"=="" set "HAS_OPENAI_API_KEY=1"
)
if not defined HAS_OPENAI_API_KEY (
  echo OPENAI_API_KEY is missing or empty in .env.
  echo Edit .env and set OPENAI_API_KEY before starting the demo.
  exit /b 1
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo Starting Atelier demo at http://%HOST%:%PORT%
"%PYTHON_EXE%" -m uvicorn app.main:app --host "%HOST%" --port "%PORT%"
