@echo off
setlocal
cd /d "%~dp0"
python -m chatweight.wechat_live --db "%~dp0chatweight.db"
pause
