@echo off
title V-reDub Studio - Launcher
echo ===================================================
echo   V-reDub Studio - khoi dong he thong...
echo ===================================================
echo.

:: Detect if ffmpeg and python venv are available
echo [1/3] Dang tim kiem moi truong Python va FFmpeg...

:: Check venv python
set PYTHON_PATH="%~dp0backend\venv\Scripts\python.exe"
if not exist %PYTHON_PATH% (
    echo [ERROR] Khong tim thay Python venv tai:
    echo %PYTHON_PATH%
    echo Vui long chay qua file setup.bat de khoi tao va cai dat thu vien truoc!
    pause
    exit /b
)
echo -- Python interpreter: OK

echo -- Dang quet va tu dong cap nhat yt-dlp (cho 5s)...
%PYTHON_PATH% -m pip install --upgrade --timeout 5 yt-dlp
echo -- yt-dlp update check completed.

:: Start Backend
echo [2/3] Dang khoi dong Backend FastAPI...
start "V-reDub Backend" cmd /k "title V-reDub Backend && %PYTHON_PATH% backend/main.py"

:: Wait for backend to start
timeout /t 4 /nobreak >nul

:: Start Frontend
echo [3/3] Dang khoi dong Frontend Vite...
start "V-reDub Frontend" cmd /k "title V-reDub Frontend && cd frontend && npm run dev"

:: Wait and open browser
timeout /t 3 /nobreak >nul
echo.
echo ===================================================
echo   He thong da san sang! Dang mo trinh duyet...
echo   Local App URL: http://localhost:5173
echo ===================================================
start http://localhost:5173

exit
