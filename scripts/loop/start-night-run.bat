@echo off
cd /d "%~dp0"
REM start-night-run.bat - one-click unattended loop launcher (owner manual trigger)
REM Driver enforces the AND gate itself (state.json.active AND authorized class);
REM if gates are closed it refuses to run. No Claude in the loop.
REM Stop: flip active=false in %USERPROFILE%\.claude\loop-control\state.json
REM       or create D:\atelier-loop\.planning\loop\LOOP-STOP

set "PATH=%USERPROFILE%\AppData\Local\Microsoft\WinGet\Links;%USERPROFILE%\.local\bin;C:\Program Files\nodejs;%USERPROFILE%\AppData\Roaming\npm;%PATH%"

if exist "D:\atelier-loop\.planning\loop\.orchestrator.lock" (
  echo [start-night-run] lock exists - an invocation may already be running. Abort.
  pause
  exit /b 1
)

echo [start-night-run] launching unattended loop driver...
start "atelier-night-run" /min "C:\Program Files\Git\bin\bash.exe" -lc "bash ~/.claude/skills/gsd-loop/lib/loop-driver-unattended.sh --project /d/atelier-loop --class atelier-backlog-slices >> /d/atelier-loop/.planning/loop/unattended-driver.out 2>&1"
echo [start-night-run] driver started in background window.
echo [start-night-run] progress: type D:\atelier-loop\.planning\loop\LOOP-LOG.md
pause
