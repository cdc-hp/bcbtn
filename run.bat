@echo off
rem Chay Web App truc tiep trong console (thay dieu khien qua dich vu Windows) - tien
rem cho phat trien/gia loi: thay log ngay, Ctrl+C de dung. Muon chay nen + icon khay he
rem thong thay vi console thi dung Chay_May_Chu.bat.
cd /d "%~dp0"
python service_windows.py run
if errorlevel 1 pause
