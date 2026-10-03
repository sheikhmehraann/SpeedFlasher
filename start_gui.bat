@echo off
setlocal enabledelayedexpansion
title SpeedFlasher (Windows 11 Fluent GUI)
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [Error] Python 3.8+ is not installed or not in system PATH.
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

python gui.py %*
