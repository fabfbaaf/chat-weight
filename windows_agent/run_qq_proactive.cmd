@echo off
setlocal
cd /d "%~dp0"
python -m chatweight.qq_proactive %*
if errorlevel 1 (
  echo.
  echo ChatWeight QQ proactive check failed. Check the configuration above.
  pause
  exit /b 1
)
