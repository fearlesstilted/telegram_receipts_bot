@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Update - Telegram Receipts Bot

echo ============================================================
echo Update aplikacji bez chmury
echo Folder: %CD%
echo ============================================================
echo.
echo Dane uzytkownika zostaja w data.
echo Konfiguracja zostaje w .env.
echo.

if not exist ".git" goto no_git

where git >nul 2>nul
if errorlevel 1 (
  echo ERROR: Git is not installed.
  echo Install Git for Windows albo podmien pliki aplikacji recznie.
  pause
  exit /b 1
)

echo Pulling latest version...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo ERROR: git pull failed. Read the message above.
  pause
  exit /b 1
)

if exist ".venv\Scripts\python.exe" (
  echo.
  echo Checking dependencies after update...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo.
echo OK. Update finished. Now run RUN_WINDOWS.bat.
pause
exit /b 0

:no_git
echo This folder is not a git clone, so automatic update is not available.
echo.
echo Manual update:
echo 1. Close RUN_WINDOWS.bat if bot is running.
echo 2. Keep these folders/files: data and .env.
echo 3. Copy new application files into this folder.
echo 4. Run RUN_WINDOWS.bat again.
echo.
pause
exit /b 0
