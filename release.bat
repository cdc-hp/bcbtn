@echo off
setlocal
cd /d "%~dp0"
for /f "usebackq delims=" %%V in ("VERSION.txt") do set APP_VERSION=%%V
if "%APP_VERSION%"=="" (
  echo VERSION.txt dang trong.
  exit /b 1
)

python -m pytest -q
if errorlevel 1 exit /b 1

git add .
git commit -m "Release v%APP_VERSION%"
if errorlevel 1 (
  echo Khong co thay doi moi hoac commit that bai.
  exit /b 1
)

git push origin main
if errorlevel 1 exit /b 1

echo Da day ma nguon. GitHub Actions se tu tao tag, Setup.exe va Release v%APP_VERSION%.
