@echo off
setlocal EnableExtensions

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

call "%ROOT_DIR%\install-page2context.cmd" --ensure --quiet
if errorlevel 1 exit /b %errorlevel%

set "VENV_PY=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [error] Missing runtime at %VENV_PY%.
  echo [hint] Run install-page2context.cmd first.
  exit /b 1
)

"%VENV_PY%" "%ROOT_DIR%\page2context.py" %*
exit /b %errorlevel%
