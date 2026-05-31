@echo off
title V-reDub Studio Installer
color 0A

echo =======================================================
echo              CHƯƠNG TRÌNH KHỞI TẠO V-REDUB STUDIO
echo =======================================================
echo.
echo Buoc 1/2: Dang setup moi truong ao Backend Python...
echo ----------------------------------------------------
cd backend
if not exist venv (
    echo [+] Dang khoi tao moi truong ao (venv)...
    python -m venv venv
) else (
    echo [~] Moi truong ao (venv) da ton tai. Quay lai tai nap...
)

echo [+] Dang kich hoat moi truong ao va tai cac thu vien python...
call venv\Scripts\activate.bat
pip install -r requirements.txt
cd ..

echo.
echo Buoc 2/2: Dang cai dat dependencies cho Frontend React...
echo -------------------------------------------------------
cd frontend
echo [+] Dang chay npm install (Vui long cho trong giay lat)...
call npm install
cd ..

echo.
echo =======================================================
echo  Setup thanh cong! Hay nhap dup 'start.bat' de chay app.
echo =======================================================
echo.
pause
