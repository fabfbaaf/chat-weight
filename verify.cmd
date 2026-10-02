@echo off
set ROOT=%~dp0
cd /d "%ROOT%windows_agent"
set PYTHONPATH=.
python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
python -m chatweight.demo
pause
