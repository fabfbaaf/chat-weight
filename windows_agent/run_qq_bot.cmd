@echo off
setlocal
cd /d "%~dp0"
python -m chatweight.qq_bot %*
if errorlevel 1 (
  echo.
  echo ChatWeight QQ bot failed. Check the configuration above.
  pause
  exit /b 1
)
