@echo off
title V-reDub Studio Launcher
color 0E

echo =======================================================
echo              KHI DOAT V-REDUB STUDIO
echo =======================================================

:: 1. Backend Launch
echo [+] Dang khoi dong Server Backend Python (Port 8000)...
start "V-reDub Backend Server" cmd /c "cd backend && call venv\Scripts\activate.bat && python main.py"

:: 2. Wait 2 seconds for backend server port bind
timeout /t 2 /nobreak > nul

:: 3. Frontend Launch
echo [+] Dang khoi dong Giao dien Frontend React...
start "V-reDub Frontend Client" cmd /c "cd frontend && npm run dev"

echo.
echo =======================================================
echo   Ung dung da khoi chay!
echo   - Backend: http://localhost:8000
echo   - Frontend: http://localhost:5173 (Trinh duyet se tu mo)
echo =======================================================
echo.
timeout /t 5
