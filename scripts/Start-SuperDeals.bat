@echo off
setlocal
if not defined SUPERDEAL_PROJECT set "SUPERDEAL_PROJECT=%USERPROFILE%\superdeal-staging"
if not exist "%SUPERDEAL_PROJECT%\scripts\start_pipeline.ps1" (
  echo Cannot find SuperDeals in "%SUPERDEAL_PROJECT%".
  echo Set SUPERDEAL_PROJECT to your existing staging folder and try again.
  pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SUPERDEAL_PROJECT%\scripts\start_pipeline.ps1"
exit /b %ERRORLEVEL%
