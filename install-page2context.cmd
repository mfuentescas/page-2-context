@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "REQ_FILE=%ROOT_DIR%\requirements.txt"
set "VENV_DIR=%ROOT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "STAMP_FILE=%VENV_DIR%\.p2cxt_install_stamp"

set "MODE=install"
set "FORCE=0"
set "QUIET=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--ensure" set "MODE=ensure"
if /I "%~1"=="--force" set "FORCE=1"
if /I "%~1"=="--quiet" set "QUIET=1"
shift
goto parse_args

:args_done
call :find_python
if not defined PY_CMD (
  echo [error] Python was not found. Install Python 3.11+ and run this installer again.
  exit /b 1
)

if not exist "%VENV_PY%" (
  "%PY_CMD%" -m venv "%VENV_DIR%"
  if errorlevel 1 exit /b 1
)

for /f "usebackq delims=" %%H in (`"%PY_CMD%" -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path(r'%REQ_FILE%').read_bytes()).hexdigest())"`) do set "REQ_HASH=%%H"
for /f "usebackq delims=" %%V in (`"%VENV_PY%" -c "import platform; print(platform.python_version())"`) do set "PY_VER=%%V"
set "PLATFORM_TAG=Windows-%PROCESSOR_ARCHITECTURE%"

set "NEEDS_INSTALL=1"
if "%FORCE%"=="0" if exist "%STAMP_FILE%" (
  call :read_stamp REQ_SHA256 STAMP_REQ
  call :read_stamp PYTHON_VERSION STAMP_PY
  call :read_stamp PLATFORM STAMP_PLATFORM
  if "!STAMP_REQ!"=="%REQ_HASH%" if "!STAMP_PY!"=="%PY_VER%" if "!STAMP_PLATFORM!"=="%PLATFORM_TAG%" set "NEEDS_INSTALL=0"
)

if "%NEEDS_INSTALL%"=="0" (
  exit /b 0
)

if not "%QUIET%"=="1" echo [info] Installing/updating Python dependencies in %VENV_DIR%
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 exit /b 1
"%VENV_PY%" -m playwright install chromium
if errorlevel 1 exit /b 1

(
  echo REQ_SHA256=%REQ_HASH%
  echo PYTHON_VERSION=%PY_VER%
  echo PLATFORM=%PLATFORM_TAG%
)>"%STAMP_FILE%"

if not "%QUIET%"=="1" echo [info] page2context runtime is ready.
exit /b 0

:find_python
set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=py -3"
)
if not defined PY_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
  where python3 >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python3"
)
exit /b 0

:read_stamp
set "%~2="
if not exist "%STAMP_FILE%" exit /b 0
for /f "usebackq tokens=1,* delims==" %%A in ("%STAMP_FILE%") do (
  if /I "%%A"=="%~1" set "%~2=%%B"
)
exit /b 0
