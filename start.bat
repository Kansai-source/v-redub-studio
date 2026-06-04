@echo off
title V-reDub Studio - Launcher
color 0E

echo =======================================================
echo              KHOI DONG V-REDUB STUDIO
echo =======================================================
echo.

:: 1. Kiem tra moi truong ao python co ton tai khong
echo [1/3] Dang tim kiem moi truong Python va FFmpeg...
set PYTHON_PATH="%~dp0backend\venv\Scripts\python.exe"
if not exist %PYTHON_PATH% (
    echo [ERROR] Khong tim thay moi truong ao Python tai duong dan: backend\venv
    echo Vui long chay file 'setup.bat' truoc de khoi tao moi truong va tai cac thu vien!
    echo.
    pause
    exit /b
)
echo -- Python interpreter: OK

:: 2. Kiem tra thu muc node_modules cua frontend co ton tai khong
if not exist "frontend\node_modules\" (
    echo [ERROR] Khong tim thay cac thu vien frontend tai: frontend\node_modules
    echo Vui long chay file 'setup.bat' truoc de cai dat cac goi dependencies!
    echo.
    pause
    exit /b
)
echo -- Node dependencies: OK

:: 3. Tu dong cap nhat yt-dlp de tranh bi loi download Youtube / phu de
echo -- Dang quet va tu dong cap nhat yt-dlp (cho 5s)...
%PYTHON_PATH% -m pip install --upgrade --timeout 5 yt-dlp
echo -- yt-dlp update check completed.

:: 4. Khoi dong Server Backend Python (Port 8000)
echo [2/3] Dang khoi dong Backend FastAPI...
start "V-reDub Backend" cmd /k "title V-reDub Backend && cd backend && call venv\Scripts\activate.bat && python main.py"

:: 5. Cho 3 giay de port backend san sang
timeout /t 3 /nobreak > nul

:: 6. Khoi dong Giao dien Frontend React
echo [3/3] Dang khoi dong Giao dien Frontend React...
start "V-reDub Frontend" cmd /k "title V-reDub Frontend && cd frontend && npm run dev"

echo.
echo =======================================================
echo   Ung dung dang duoc tai len!
echo   - Backend API: http://localhost:8000
echo   - Frontend UI: http://localhost:5173 (Trinh duyet se mo sau 3s)
echo =======================================================
echo.
timeout /t 3 /nobreak > nul
start http://localhost:5173

exit
