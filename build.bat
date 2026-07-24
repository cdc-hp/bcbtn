@echo off
setlocal EnableExtensions
cd /d "%~dp0"

for /f "usebackq delims=" %%V in ("VERSION.txt") do set "APP_VERSION=%%V"
if "%APP_VERSION%"=="" set "APP_VERSION=0.0.0"
set "SETUP_FILE=setup_output\GiamSatDichBenh-Setup-v%APP_VERSION%.exe"
set "SETUP_SERVER_FILE=setup_output\GiamSatDichBenh-Server-Setup-v%APP_VERSION%.exe"
set "SETUP_ADMIN_FILE=setup_output\GiamSatDichBenh-Admin-Setup-v%APP_VERSION%.exe"
set "SETUP_WEBAPP_FILE=setup_output\CDC-GiamSatDichBenh-Server-Setup-v%APP_VERSION%.exe"

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist dist_cdc_service rmdir /s /q dist_cdc_service
if exist setup_output rmdir /s /q setup_output

python -m PyInstaller --noconfirm --clean --windowed ^
  --name GiamSatDichBenh ^
  --collect-all PyQt6 ^
  --hidden-import PyQt6.QtCharts ^
  app.py
if errorlevel 1 goto :error

rem KHONG sao chep data, backups, Excel hay CSDL vao ban phat hanh.
copy /Y VERSION.txt "dist\GiamSatDichBenh\VERSION.txt" >nul
if errorlevel 1 goto :error
copy /Y README.md "dist\GiamSatDichBenh\README.md" >nul
if errorlevel 1 goto :error

rem Web App tap trung (Giai doan 9, xem TASKS.md) - dich vu Windows chay webapp/ qua Uvicorn,
rem entrypoint la service_windows.py (khong phai app.py). --exclude-module PyQt5/PyQt6: moi
rem truong build co the co ca 2 (vd. may dev cai PyQt5 rieng) khien PyInstaller tu choi build vi
rem xung dot Qt binding - webapp/ khong dung Qt nen loai han cho chac.
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

rem 3 ban cai desktop cu dung chung dist\GiamSatDichBenh, chi khac cau hinh mac dinh installer
rem ghi ra (xem TASKS.md - giu song song cho toi Giai doan 11):
rem   setup.iss         - ban tong hop, hoi chon 1 trong 3 che do (giu nguyen cho may don le)
rem   setup-server.iss  - rieng che do May chu LAN, cai duy nhat 1 lan
rem   setup-admin.iss   - rieng che do May tram quan tri
rem Ban cai Web App tap trung (Giai doan 9, MOI, dung dist_cdc_service):
rem   setup-webapp-server.iss - dich vu Windows, quan tri hoan toan qua trinh duyet
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup.iss
if errorlevel 1 goto :error
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup-server.iss
if errorlevel 1 goto :error
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup-admin.iss
if errorlevel 1 goto :error
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup-webapp-server.iss
if errorlevel 1 goto :error

if not exist "%SETUP_FILE%" (
  echo Khong tim thay bo cai mong doi: %SETUP_FILE%
  if exist setup_output dir /b setup_output
  goto :error
)
if not exist "%SETUP_SERVER_FILE%" (
  echo Khong tim thay bo cai mong doi: %SETUP_SERVER_FILE%
  if exist setup_output dir /b setup_output
  goto :error
)
if not exist "%SETUP_ADMIN_FILE%" (
  echo Khong tim thay bo cai mong doi: %SETUP_ADMIN_FILE%
  if exist setup_output dir /b setup_output
  goto :error
)
if not exist "%SETUP_WEBAPP_FILE%" (
  echo Khong tim thay bo cai mong doi: %SETUP_WEBAPP_FILE%
  if exist setup_output dir /b setup_output
  goto :error
)

echo Hoan tat.
echo Portable (desktop cu): dist\GiamSatDichBenh\GiamSatDichBenh.exe
echo Setup (tong hop 3 che do, desktop cu): %SETUP_FILE%
echo Setup (May chu LAN, desktop cu): %SETUP_SERVER_FILE%
echo Setup (May tram quan tri, desktop cu): %SETUP_ADMIN_FILE%
echo Setup (Web App tap trung, dich vu Windows): %SETUP_WEBAPP_FILE%
exit /b 0

:error
echo Build that bai.
exit /b 1
