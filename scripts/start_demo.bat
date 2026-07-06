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

powershell -NoProfile -ExecutionPolicy Bypass -Command "$line = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^\s*OPENAI_API_KEY\s*=' } | Select-Object -Last 1; if ($null -eq $line) { exit 1 }; $value = ($line -split '=', 2)[1].Trim().Trim([char]34).Trim([char]39).Trim(); if ([string]::IsNullOrWhiteSpace($value)) { exit 1 }; exit 0"
if errorlevel 1 (
  echo OPENAI_API_KEY is missing or empty in .env.
  echo Edit .env and set OPENAI_API_KEY before starting the demo.
  exit /b 1
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo Starting Atelier demo at http://%HOST%:%PORT%
"%PYTHON_EXE%" -m uvicorn app.main:app --host "%HOST%" --port "%PORT%"
