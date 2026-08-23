@echo off
title Codeforces Auto Uploader
cd /d "%~dp0"
if exist ".\.venv\bin\python.exe" (
    ".\.venv\bin\python.exe" run.py
) else if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" run.py
) else (
    python run.py
)
pause
