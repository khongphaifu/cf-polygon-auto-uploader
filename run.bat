@echo off
title Codeforces ^& Polygon Auto Uploader
cd /d "%~dp0"

set PYTHON_EXE=python
if exist ".\.venv\bin\python.exe" (
    set PYTHON_EXE=".\.venv\bin\python.exe"
) else if exist ".\.venv\Scripts\python.exe" (
    set PYTHON_EXE=".\.venv\Scripts\python.exe"
)

echo =======================================================
echo    CODEFORCES ^& POLYGON AUTO UPLOADER SUITE
echo =======================================================
echo.
echo  [1] Mo Giao dien Web Dashboard (Trinh duyet http://127.0.0.1:8080)
echo  [2] Chay Giao dien CLI Terminal
echo  [3] Chay danh sach link tu file urls.txt
echo  [0] Thoat
echo.
set /p opt="Nhap lua chon cua ban (Mac dinh la 1): "

if "%opt%"=="" set opt=1
if "%opt%"=="1" (
    echo Dang khoi dong Web Dashboard...
    %PYTHON_EXE% ui/web_app.py
) else if "%opt%"=="2" (
    %PYTHON_EXE% run.py
) else if "%opt%"=="3" (
    %PYTHON_EXE% run.py --batch urls.txt
) else (
    exit /b 0
)

pause
