@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Reset Excel - Telegram Receipts Bot

echo ============================================================
echo Reset tabeli Excel
echo Folder: %CD%
echo ============================================================
echo.
echo Ten reset archiwizuje stare rows.jsonl / Excel do data\archive.
echo Zdjecia w data\receipts zostaja na miejscu.
echo.
set /p CONFIRM=Type RESET and press Enter to continue: 
if /I not "%CONFIRM%"=="RESET" (
  echo Cancelled.
  pause
  exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv is missing. Run RUN_WINDOWS.bat first.
  pause
  exit /b 1
)

set PYTHONPATH=src
.venv\Scripts\python.exe -m telegram_receipts_bot.reset_excel
if errorlevel 1 (
  echo.
  echo FAILED. Read the error above.
  pause
  exit /b 1
)

echo.
echo OK. Excel has been reset.
pause
