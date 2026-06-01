@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Diagnoza - Telegram Receipts Bot

echo ============================================================
echo DIAGNOZA - Bot do paragonow
echo Folder: %CD%
echo ============================================================
echo.
echo Ten plik sprawdza instalacje i (jesli to mozliwe) testuje OCR.
echo Wynik zapisuje sie tez do logs\diagnoza.txt
echo.

if not exist "logs" mkdir logs

rem --- Find a working Python 3.11 (same logic as RUN_WINDOWS.bat) ---
set PYTHON_CMD=

where py >nul 2>nul
if not errorlevel 1 (
  py -3.11 --version >nul 2>nul
  if not errorlevel 1 set PYTHON_CMD=py -3.11
)

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set PYTHON_CMD=python
)

rem --- Prefer the project venv if it exists ---
if exist ".venv\Scripts\python.exe" (
  set RUN_PY=.venv\Scripts\python.exe
) else (
  if defined PYTHON_CMD (
    set RUN_PY=%PYTHON_CMD%
  ) else (
    echo BLAD: Nie znaleziono Pythona ani srodowiska .venv.
    echo Najpierw uruchom RUN_WINDOWS.bat, aby zainstalowac aplikacje.
    echo.
    pause
    exit /b 1
  )
)

rem --- Flags that avoid the known Windows/CPU Paddle crash (set before import) ---
set PYTHONPATH=src
set FLAGS_use_mkldnn=0
set FLAGS_use_onednn=0
set FLAGS_enable_pir_api=0

echo Uruchamiam diagnoze...
echo.
%RUN_PY% -m telegram_receipts_bot.doctor
set DIAG_EXIT=%ERRORLEVEL%

echo.
if "%DIAG_EXIT%"=="0" (
  echo Diagnoza zakonczona. Instalacja wyglada dobrze.
) else (
  echo Diagnoza wykryla problem z instalacja. Przeczytaj wiersze [BLAD] powyzej.
  echo Mozesz wyslac plik logs\diagnoza.txt po pomoc.
)
echo.
pause
exit /b %DIAG_EXIT%
