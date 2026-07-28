@echo off
rem Chay Web App thu cong, thu vao khay he thong - xem service_tray.py.
rem Dung cho may demo/phat trien hoac truoc khi cai dat dich vu Windows chinh thuc
rem (setup-webapp-server.iss). Trien khai CDC that nen dung dich vu Windows (tu khoi
rem dong cung may), khong can ai dang nhap desktop.
cd /d "%~dp0"
pythonw service_tray.py
