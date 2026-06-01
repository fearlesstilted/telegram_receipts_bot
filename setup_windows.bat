@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" is not installed.
  echo Install Python 3.11 from python.org and enable "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example. Fill TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_ID.
)

if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Could not create venv with Python 3.11.
    echo Install Python 3.11 and try again.
    pause
    exit /b 1
  )
)

.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo Setup complete.
echo Edit .env if TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_CHAT_ID is empty.
pause
