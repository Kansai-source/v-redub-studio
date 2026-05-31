@echo off
title V-reDub Studio Launcher
color 0E

echo =======================================================
echo              KHOI DONG V-REDUB STUDIO
echo =======================================================
echo.

:: 1. Kiem tra moi truong ao python co ton tai khong
if not exist "backend\venv\Scripts\python.exe" (
    echo [ERROR] Khong tim thay moi truong ao Python tai duong dan: backend\venv
    echo Vui long chay file 'setup.bat' truoc de khoi tao moi truong va tai cac thu vien!
    echo.
    pause
    exit /b
)

:: 2. Kiem tra thu muc node_modules cua frontend co ton tai khong
if not exist "frontend\node_modules\" (
    echo [ERROR] Khong tim thay cac thu vien frontend tai: frontend\node_modules
    echo Vui long chay file 'setup.bat' truoc de cai dat cac goi dependencies!
    echo.
    pause
    exit /b
)

:: 3. Khoi dong Server Backend Python (Port 8000)
echo [+] Dang khoi dong Server Backend Python (Port 8000)...
start "V-reDub Backend Server" cmd /k "cd backend && call venv\Scripts\activate.bat && python main.py"

:: 4. Cho 2 giay de port backend san sang
timeout /t 2 /nobreak > nul

:: 5. Khoi dong Giao dien Frontend React
echo [+] Dang khoi dong Giao dien Frontend React...
start "V-reDub Frontend Client" cmd /k "cd frontend && npm run dev"

echo.
echo =======================================================
echo   Ung dung dang duoc tai len!
echo   - Backend API: http://localhost:8000
echo   - Frontend UI: http://localhost:5173 (Trinh duyet se mo sau 3s)
echo =======================================================
echo.
timeout /t 3 /nobreak > nul
start http://localhost:5173
