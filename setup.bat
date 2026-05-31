@echo off
title V-reDub Studio Installer
color 0A

echo =======================================================
echo              CHUONG TRINH KHOI TAO V-REDUB STUDIO
echo =======================================================
echo.

:: 1. Kiem tra va tu dong cai dat Node.js qua winget neu chua co
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Khong tim thay Node.js tren he thong.
    echo [+] Dang tien hanh tu dong tai va cai dat Node.js qua Windows winget...
    winget install OpenJS.NodeJS --accept-package-agreements --accept-source-agreements
    if %errorlevel% equ 0 (
        echo [+] Cai dat Node.js thanh cong!
        echo [!] LUU Y: Vui long tat cua so CMD nay di va nhap dup chuot chay lai file setup.bat de nap bien moi truong.
        pause
        exit /b
    ) else (
        echo [ERROR] Khong the tu dong cai dat Node.js.
        echo Vui long tai va cai dat thu cong tu trang chu: https://nodejs.org/
        pause
        exit /b
    )
) else (
    echo [~] Kiem tra Node.js: OK (Version: )
    node -v
)

:: 2. Kiem tra va tu dong cai dat FFmpeg qua winget neu chua co
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Khong tim thay FFmpeg tren he thong.
    echo [+] Dang tien hanh tu dong tai va cai dat FFmpeg qua Windows winget...
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    if %errorlevel% equ 0 (
        echo [+] Cai dat FFmpeg thanh cong!
        echo [!] LUU Y: Vui long tat cua so CMD nay di va nhap dup chuot chay lai file setup.bat de nap bien moi truong.
        pause
        exit /b
    ) else (
        echo [ERROR] Khong the tu dong cai dat FFmpeg.
        echo Vui long tai thu cong hoac chay lenh thu cong: winget install Gyan.FFmpeg
        pause
        exit /b
    )
) else (
    echo [~] Kiem tra FFmpeg: OK
)

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
