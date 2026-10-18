@echo off
setlocal enabledelayedexpansion
title SpeedFlasher
cd /d "%~dp0"

call "%~dp0setup.bat"
if %errorlevel% neq 0 (
    echo.
    echo [Error] SpeedFlasher environment setup failed.
    pause
    exit /b %errorlevel%
)

if "!PYTHON_CMD!"=="py -3" (
    set "RUN_CMD=py -3"
) else if defined PYTHON_CMD (
    set "RUN_CMD="!PYTHON_CMD!""
) else (
    set "RUN_CMD=python"
)

!RUN_CMD! "%~dp0main.py" %*
set "EXIT_CODE=%errorlevel%"

if %EXIT_CODE% neq 0 (
    echo.
    echo [!] SpeedFlasher exited with error code %EXIT_CODE%.
    pause
) else if "%~1"=="" (
    echo.
    pause
)
exit /b %EXIT_CODE%
