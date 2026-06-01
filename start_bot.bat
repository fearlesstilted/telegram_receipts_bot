@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. Run setup_windows.bat first.
  pause
  exit /b 1
)

if exist "data\bot.lock" (
  echo Bot already looks running from this project.
  echo Stop the old window with Ctrl+C, or delete data\bot.lock if it is stale.
  pause
  exit /b 1
)

if not exist "data" mkdir data
mkdir "data\bot.lock" >nul 2>nul
if errorlevel 1 (
  echo Cannot create data\bot.lock.
  pause
  exit /b 1
)

set PYTHONPATH=src
set FLAGS_use_mkldnn=0
set FLAGS_use_onednn=0
set FLAGS_enable_pir_api=0

.venv\Scripts\python.exe -m telegram_receipts_bot.main

rmdir "data\bot.lock" >nul 2>nul
pause
