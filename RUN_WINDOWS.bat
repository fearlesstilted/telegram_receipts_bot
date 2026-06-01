@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Telegram Receipts Bot

echo ============================================================
echo Telegram Receipts Bot - local Windows launcher
echo Folder: %CD%
echo ============================================================
echo.

if not exist "logs" mkdir logs
set LOG_FILE=logs\windows_run.log
echo [%DATE% %TIME%] Launcher started > "%LOG_FILE%"
set PYTHON_CMD=

call :check_env_file || goto fail
call :check_python || goto fail
call :ensure_venv || goto fail
call :install_dependencies || goto fail
call :show_versions || goto fail
call :check_env_values || goto fail
call :start_bot || goto fail
goto end

:check_env_file
echo [1/7] Checking .env file...
if exist ".env.txt" (
  echo Found .env.txt. Windows probably saved the config with hidden .txt extension.
  if not exist ".env" (
    copy ".env.txt" ".env" >nul
    echo Copied .env.txt to .env
  ) else (
    echo .env already exists. Leaving .env.txt unchanged.
  )
)

if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example
  ) else (
    echo ERROR: .env and .env.example are missing.
    exit /b 1
  )
)
echo OK: .env exists.
echo.
exit /b 0

:check_python
echo [2/7] Checking Python 3.11...

where py >nul 2>nul
if not errorlevel 1 (
  py -3.11 --version >> "%LOG_FILE%" 2>&1
  if not errorlevel 1 (
    set PYTHON_CMD=py -3.11
    py -3.11 --version
    echo.
    exit /b 0
  )
)

where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >> "%LOG_FILE%" 2>&1
  if not errorlevel 1 (
    set PYTHON_CMD=python
    python --version
    echo.
    exit /b 0
  )
)

where python3 >nul 2>nul
if not errorlevel 1 (
  python3 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >> "%LOG_FILE%" 2>&1
  if not errorlevel 1 (
    set PYTHON_CMD=python3
    python3 --version
    echo.
    exit /b 0
  )
)

echo ERROR: Python 3.11 was not found.
echo Install Python 3.11 from python.org.
echo During install, enable "Add python.exe to PATH".
echo If Python is installed from Microsoft Store, uninstall it and install from python.org.
echo.
exit /b 1

:ensure_venv
echo [3/7] Checking virtual environment...
if exist ".venv\Scripts\python.exe" (
  echo OK: .venv already exists.
  echo.
  exit /b 0
)

echo Creating .venv...
%PYTHON_CMD% -m venv .venv >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo ERROR: Could not create .venv. See %LOG_FILE%
  exit /b 1
)
echo OK: .venv created.
echo.
exit /b 0

:install_dependencies
echo [4/7] Checking dependencies...
.venv\Scripts\python.exe -c "import telegram, dotenv, PIL, paddle, paddleocr, numpy" >> "%LOG_FILE%" 2>&1
if not errorlevel 1 (
  echo OK: dependencies already installed.
  echo.
  exit /b 0
)

echo Installing dependencies. This can take several minutes on first run...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
  echo ERROR: pip upgrade failed.
  exit /b 1
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: dependency installation failed.
  echo See %LOG_FILE% and the messages above.
  exit /b 1
)

.venv\Scripts\python.exe -c "import telegram, dotenv, PIL, paddle, paddleocr, numpy"
if errorlevel 1 (
  echo ERROR: dependencies installed but import check still fails.
  exit /b 1
)
echo OK: dependencies installed.
echo.
exit /b 0

:show_versions
echo [5/7] Runtime versions...
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -c "import paddle, paddleocr, numpy; print('paddlepaddle', paddle.__version__); print('paddleocr', paddleocr.__version__); print('numpy', numpy.__version__)"
if errorlevel 1 (
  echo ERROR: cannot print runtime versions.
  exit /b 1
)
echo.
exit /b 0

:check_env_values
echo [6/7] Checking bot config...
findstr /R /C:"^TELEGRAM_BOT_TOKEN=..*" ".env" >nul
if errorlevel 1 (
  findstr /R /C:"^TELEGRAM_BOT_TOKEN=..*" ".env.example" >nul
  if not errorlevel 1 (
    echo .env has empty token, but .env.example has values. Copying .env.example to .env...
    copy ".env.example" ".env" >nul
  )
)

findstr /R /C:"^TELEGRAM_BOT_TOKEN=..*" ".env" >nul
if errorlevel 1 (
  echo ERROR: TELEGRAM_BOT_TOKEN is empty in .env
  echo Open .env and fill TELEGRAM_BOT_TOKEN=...
  exit /b 1
)

findstr /R /C:"^TELEGRAM_ALLOWED_CHAT_ID=..*" ".env" >nul
if errorlevel 1 (
  findstr /R /C:"^TELEGRAM_ALLOWED_CHAT_ID=..*" ".env.example" >nul
  if not errorlevel 1 (
    echo .env has empty chat id, but .env.example has values. Copying .env.example to .env...
    copy ".env.example" ".env" >nul
  )
)

findstr /R /C:"^TELEGRAM_ALLOWED_CHAT_ID=..*" ".env" >nul
if errorlevel 1 (
  echo ERROR: TELEGRAM_ALLOWED_CHAT_ID is empty in .env
  echo Open .env and fill TELEGRAM_ALLOWED_CHAT_ID=...
  exit /b 1
)
echo OK: token and allowed chat id are set.
echo.
exit /b 0

:start_bot
echo [7/7] Starting Telegram bot...
echo.
echo Keep this window open while using the bot.
echo Stop: press Ctrl+C in this window.
echo.

if exist "data\bot.lock" (
  echo WARNING: data\bot.lock exists.
  echo If the bot is not running, delete data\bot.lock and run this file again.
  exit /b 1
)

if not exist "data" mkdir data
mkdir "data\bot.lock" >nul 2>nul
if errorlevel 1 (
  echo ERROR: Cannot create data\bot.lock.
  exit /b 1
)

set PYTHONPATH=src
set FLAGS_use_mkldnn=0
set FLAGS_use_onednn=0
set FLAGS_enable_pir_api=0

.venv\Scripts\python.exe -m telegram_receipts_bot.main
set BOT_EXIT=%ERRORLEVEL%
rmdir "data\bot.lock" >nul 2>nul

if not "%BOT_EXIT%"=="0" (
  echo.
  echo ERROR: Bot stopped with code %BOT_EXIT%.
  exit /b %BOT_EXIT%
)
exit /b 0

:fail
echo.
echo ============================================================
echo FAILED. Read the error above.
echo Log file: %LOG_FILE%
echo ============================================================
pause
exit /b 1

:end
echo.
echo Bot stopped.
pause
