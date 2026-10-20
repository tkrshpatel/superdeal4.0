@echo off
setlocal
cd /d "%~dp0.."

if not exist .venv\Scripts\python.exe (
  echo Creating SuperDeal Python environment...
  py -3.11 -m venv .venv
  if errorlevel 1 goto :error
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -e .
  if errorlevel 1 goto :error
)

set SUPERDEAL_API_HOST=0.0.0.0
set SUPERDEAL_API_PORT=8000
set SUPERDEAL_DB=data\superdeal.db

echo.
echo SuperDeal API starting on port 8000...
echo Phone and PC must be on the same Wi-Fi/LAN.
echo Find the PC IPv4 address with: ipconfig
.venv\Scripts\python.exe -m superdeal.server
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo SuperDeal API could not start. Check the message above.
pause
exit /b 1
