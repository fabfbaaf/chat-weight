@echo off
setlocal
cd /d "%~dp0"
python -m chatweight.inspect_db --db "%~dp0chatweight.db" --limit 50
pause
