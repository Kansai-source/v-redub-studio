@echo off
title V-reDub Studio Installer
color 0A

echo =======================================================
echo              CHUONG TRINH KHOI TAO V-REDUB STUDIO
echo =======================================================
echo.

:: 1. Kiem tra va tu dong cai dat Python qua winget neu chua co
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [~] Kiem tra Python: OK
    goto :check_node
)

echo [!] Khong tim thay Python tren he thong.
echo [+] Dang tien hanh tu dong tai va cai dat Python 3.11 qua Windows winget...
winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
if %errorlevel% equ 0 (
    echo [+] Cai dat Python thanh cong!
    echo [!] LUU Y: Vui long tat cua so CMD nay di va nhap dup chuot chay lai file setup.bat de bat dau buoc tiep theo.
    pause
    exit /b
)

echo [ERROR] Khong the tu dong cai dat Python.
echo Vui long tai va cai dat thu cong tu trang chu: https://www.python.org/downloads/
echo LUU Y: Nho tich chon "Add python.exe to PATH" truoc khi bam Install.
pause
exit /b

:check_node
:: 2. Kiem tra va tu dong cai dat Node.js qua winget neu chua co
node -v >nul 2>&1
if %errorlevel% equ 0 (
    echo [~] Kiem tra Node.js: OK
    goto :check_ffmpeg
)

echo [!] Khong tim thay Node.js tren he thong.
echo [+] Dang tien hanh tu dong tai va cai dat Node.js qua Windows winget...
winget install OpenJS.NodeJS --accept-package-agreements --accept-source-agreements
if %errorlevel% equ 0 (
    echo [+] Cai dat Node.js thanh cong!
    echo [!] LUU Y: Vui long tat cua so CMD nay di va nhap dup chuot chay lai file setup.bat de bat dau buoc tiep theo.
    pause
    exit /b
)

echo [ERROR] Khong the tu dong cai dat Node.js.
echo Vui long tai va cai dat thu cong tu trang chu: https://nodejs.org/
pause
exit /b

:check_ffmpeg
:: 3. Kiem tra va tu dong cai dat FFmpeg qua winget neu chua co
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo [~] Kiem tra FFmpeg: OK
    goto :check_vc
)

echo [!] Khong tim thay FFmpeg tren he thong.
echo [+] Dang tien hanh tu dong tai va cai dat FFmpeg qua Windows winget...
winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
if %errorlevel% equ 0 (
    echo [+] Cai dat FFmpeg thanh cong!
    echo [!] LUU Y: Vui long tat cua so CMD nay di va nhap dup chuot chay lai file setup.bat de nap bien moi truong.
    pause
    exit /b
)

echo [ERROR] Khong the tu dong cai dat FFmpeg.
echo Vui long tai thu cong hoac chay lenh thu cong: winget install Gyan.FFmpeg
pause
exit /b

:check_vc
:: 3.5 Check Visual C++ Redistributable
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v "Version" >nul 2>nul
if %errorlevel% neq 0 (
    reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v "Version" >nul 2>nul
)
if %errorlevel% neq 0 (
    echo [!] Khong tim thay Microsoft Visual C++ Redistributable tren he thong.
    echo [+] Dang tien hanh tu dong tai va cai dat qua Windows winget...
    winget install Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements
    if %errorlevel% equ 0 (
        echo.
        echo [+] Cai dat Visual C++ Redistributable thanh cong!
        echo [!] LUU Y: Vui long tat cua so CMD nay di va chay lai setup.bat.
        echo.
        pause
        exit /b
    ) else (
        echo [WARNING] Khong the tai tu dong. Vui long tai va cai dat thu cong tu:
        echo --^> https://aka.ms/vs/17/release/vc_redist.x64.exe
        echo.
        pause
    )
) else (
    echo [~] Kiem tra Visual C++ Redistributable: OK
)

:start_installation


echo.

echo Buoc 1/2: Dang setup moi truong ao Backend Python...
echo ----------------------------------------------------
cd backend

:: Xoa venv cu neu no bi loi hoac tro trung vao folder rac
if exist venv (
    if not exist venv\Scripts\python.exe (
        echo [!] Phat hien thu muc venv loi - khong co python.exe. Tien hanh don dep va tao lai...
        rd /s /q venv
    )
)

if not exist venv (
    echo [+] Dang khoi tao moi truong ao venv...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Khong the khoi tao venv.
        echo Vui long kiem tra xem Python cua ban co bi loi khong, hoac cai dat lai Python tu trang chu.
        cd ..
        pause
        exit /b
    )
) else (
    echo [~] Moi truong ao venv da ton tai. Quay lai tai nap...
)

echo [+] Kich hoat moi truong ao va tai cac thu vien python...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Kich hoat moi truong ao venv khong thanh cong.
    cd ..
    pause
    exit /b
)

echo [+] Dang cai dat requirements (Co the mat 1-2 phut)...
nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    echo [+] Phat hien GPU NVIDIA tren he thong. Dang uu tien cai dat PyTorch phien ban CUDA 12.4...
    pip install torch --index-url https://download.pytorch.org/whl/cu124
) else (
    echo [-] Khong tim thay GPU NVIDIA hoac GPU driver. Cai dat PyTorch phien ban CPU thong thuong...
)
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Cai dat cac thu vien Python that bai.
    cd ..
    pause
    exit /b
)
cd ..

echo.
echo Buoc 2/2: Dang cai dat dependencies cho Frontend React...
echo -------------------------------------------------------
cd frontend
echo [+] Dang chay npm install (Vui long cho trong giay lat)...
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] Cai dat cac goi npm cho Frontend that bai.
    cd ..
    pause
    exit /b
)
cd ..

echo.
echo =======================================================
echo  Setup thanh cong! Hay nhap dup 'start.bat' de chay app.
echo =======================================================
echo.
pause
