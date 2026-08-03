@echo off
setlocal EnableExtensions
title Khoi dong CDC Giam Sat Dich Benh
cd /d "%~dp0"

rem Copy file nay vao dung thu muc da cai dat (vi du C:\CDC-GiamSatDichBenh, cung thu muc voi
rem CDCGiamSatDichBenh.exe) roi chay - dung khi dich vu Windows bi dung (vi du sau khi tat may,
rem loi, hoac ai do lo bam Stop) ma khong muon mo Services.msc thu cong.

rem Kiem tra dang chay voi quyen Administrator (can de dieu khien dich vu Windows).
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo ============================================================
  echo  CAN CHAY VOI QUYEN ADMINISTRATOR.
  echo  Chuot phai vao file nay, chon "Run as administrator", roi thu lai.
  echo ============================================================
  pause
  exit /b 1
)

if not exist "%~dp0CDCGiamSatDichBenh.exe" (
  echo ============================================================
  echo  KHONG TIM THAY CDCGiamSatDichBenh.exe trong thu muc nay.
  echo  Hay copy file .bat nay vao dung thu muc da cai dat may chu
  echo  (vi du C:\CDC-GiamSatDichBenh) roi chay lai.
  echo ============================================================
  pause
  exit /b 1
)

echo Dang khoi dong dich vu CDCGiamSatDichBenh...
"%~dp0CDCGiamSatDichBenh.exe" start
set "RESULT=%errorlevel%"

echo.
if "%RESULT%"=="0" (
  echo Da khoi dong dich vu thanh cong.
  echo Mo trang quan tri qua shortcut "Mo trang quan tri" trong Start Menu,
  echo hoac vao http://127.0.0.1:<cong da cau hinh>/cdc/login
) else (
  echo Khoi dong that bai - xem thong bao loi o tren.
  echo Neu thong bao noi dich vu da chay roi thi khong can lam gi them.
)
pause
exit /b %RESULT%
