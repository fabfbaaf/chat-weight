@echo off
setlocal
cd /d "%~dp0"
python --version
python -m pip install --upgrade pip
python -m pip install -e ".[wechat-windows]"
if errorlevel 1 (
  echo.
  echo Installation failed. Use Python 3.11 or 3.12 on Windows 10/11.
  pause
  exit /b 1
)
echo.
echo ChatWeight WeChat Windows dependencies installed.
pause
