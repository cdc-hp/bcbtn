@echo off
setlocal EnableExtensions
title Cap nhat CDC Giam Sat Dich Benh
cd /d "%~dp0"

rem Kiem tra dang chay voi quyen Administrator (can de bo cai dang ky lai dich vu Windows).
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo ============================================================
  echo  CAN CHAY VOI QUYEN ADMINISTRATOR.
  echo  Chuot phai vao file nay, chon "Run as administrator", roi thu lai.
  echo ============================================================
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Cap_Nhat_May_Chu.ps1"
set "RESULT=%errorlevel%"

echo.
if "%RESULT%"=="0" (
  echo Cap nhat thanh cong.
) else (
  echo Cap nhat that bai - xem thong bao loi o tren.
)
pause
exit /b %RESULT%
