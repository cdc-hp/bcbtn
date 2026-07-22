@echo off
setlocal EnableExtensions
cd /d "%~dp0"

for /f "usebackq delims=" %%V in ("VERSION.txt") do set "APP_VERSION=%%V"
if "%APP_VERSION%"=="" set "APP_VERSION=0.0.0"
set "SETUP_FILE=setup_output\GiamSatDichBenh-Setup-v%APP_VERSION%.exe"
set "SETUP_SERVER_FILE=setup_output\GiamSatDichBenh-Server-Setup-v%APP_VERSION%.exe"
set "SETUP_ADMIN_FILE=setup_output\GiamSatDichBenh-Admin-Setup-v%APP_VERSION%.exe"

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
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

rem 3 ban cai dung chung dist\GiamSatDichBenh, chi khac cau hinh mac dinh installer ghi ra:
rem   setup.iss         - ban tong hop, hoi chon 1 trong 3 che do (giu nguyen cho may don le)
rem   setup-server.iss  - rieng che do May chu, cai duy nhat 1 lan
rem   setup-admin.iss   - rieng che do May tram quan tri
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup.iss
if errorlevel 1 goto :error
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup-server.iss
if errorlevel 1 goto :error
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% setup-admin.iss
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

echo Hoan tat.
echo Portable: dist\GiamSatDichBenh\GiamSatDichBenh.exe
echo Setup (tong hop 3 che do): %SETUP_FILE%
echo Setup (May chu): %SETUP_SERVER_FILE%
echo Setup (May tram quan tri): %SETUP_ADMIN_FILE%
exit /b 0

:error
echo Build that bai.
exit /b 1
