@echo off
setlocal enabledelayedexpansion
title SpeedFlasher
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [Error] Python 3.8+ is not installed or not in system PATH.
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

python main.py %*

if "%~1"=="" (
    echo.
    pause
)
