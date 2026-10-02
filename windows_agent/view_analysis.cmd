@echo off
python -m chatweight.manage people

echo.
echo Pending relationship review items:
python -m chatweight.manage pending --limit 20
