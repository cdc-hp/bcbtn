@echo off
setlocal EnableExtensions
cd /d "%~dp0"

for /f "usebackq delims=" %%V in ("VERSION.txt") do set "APP_VERSION=%%V"
if "%APP_VERSION%"=="" set "APP_VERSION=0.0.0"
set "SETUP_WEBAPP_FILE=setup_output\CDC-GiamSatDichBenh-Server-Setup-v%APP_VERSION%.exe"

if exist build rmdir /s /q build
if exist dist_cdc_service rmdir /s /q dist_cdc_service
if exist setup_output rmdir /s /q setup_output

rem Web App tap trung (Giai doan 9, xem TASKS.md) - dich vu Windows chay webapp/ qua Uvicorn,
rem entrypoint la service_windows.py. --exclude-module PyQt5/PyQt6: moi truong build co the co
rem san 1 trong 2 (vd. cai chung voi du an khac) khien PyInstaller tu choi build vi xung dot Qt
rem binding - webapp/ khong dung Qt nen loai han cho chac.
python -m PyInstaller --noconfirm --clean --console ^
  --name CDCGiamSatDichBenh ^
  --distpath dist_cdc_service ^
  --add-data "webapp/templates;webapp/templates" ^
  --add-data "webapp/static;webapp/static" ^
  --hidden-import webapp.main ^
  --hidden-import win32timezone ^
  --hidden-import multipart ^
  --hidden-import python_multipart ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all uvicorn ^
  --collect-all apscheduler ^
  --exclude-module PyQt5 ^
  --exclude-module PyQt6 ^
  service_windows.py
if errorlevel 1 goto :error

copy /Y VERSION.txt "dist_cdc_service\CDCGiamSatDichBenh\VERSION.txt" >nul
if errorlevel 1 goto :error
copy /Y README.md "dist_cdc_service\CDCGiamSatDichBenh\README.md" >nul
if errorlevel 1 goto :error

set "ISCC_PATH="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC_PATH set "ISCC_PATH=%%I"
if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH (
  echo Khong tim thay Inno Setup 6.
  goto :error
)

echo Inno Setup: %ISCC_PATH%

rem Ban cai DUY NHAT: Web App tap trung, dung dich vu Windows (xem TASKS.md).
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup-webapp-server.iss
if errorlevel 1 goto :error

if not exist "%SETUP_WEBAPP_FILE%" (
  echo Khong tim thay bo cai mong doi: %SETUP_WEBAPP_FILE%
  if exist setup_output dir /b setup_output
  goto :error
)

echo Hoan tat.
echo Setup (Web App tap trung, dich vu Windows): %SETUP_WEBAPP_FILE%
exit /b 0

:error
echo Build that bai.
exit /b 1
