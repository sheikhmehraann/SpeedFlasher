@echo off
setlocal enabledelayedexpansion

echo ========================================================================
echo                         SpeedFlasher Setup
echo ========================================================================

set "FOUND_PYTHON="

:: 1. Check if 'python' in PATH is valid (not WindowsApps stub)
where python >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        echo "%%i" | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            "%%i" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
            if not errorlevel 1 (
                set "FOUND_PYTHON=%%i"
                goto :PythonFound
            )
        )
    )
)

:: 2. Check Python Launcher 'py -3'
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "FOUND_PYTHON=py -3"
        goto :PythonFound
    )
)

:: 3. Scan standard installation folders
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "FOUND_PYTHON=%%D\python.exe"
            goto :PythonFound
        )
    )
)

for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "FOUND_PYTHON=%%D\python.exe"
            goto :PythonFound
        )
    )
)

for /d %%D in ("C:\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "FOUND_PYTHON=%%D\python.exe"
            goto :PythonFound
        )
    )
)

:: 4. If Python is still not found, install it automatically
echo [*] Python was not found on your system.
echo [*] SpeedFlasher will now download and install Python 3.11 automatically.
echo [*] Please wait a moment...
echo.

set "INSTALL_SUCCESS=0"

:: Try winget first if available
where winget >nul 2>nul
if %errorlevel% equ 0 (
    echo [*] Attempting install via Windows Package Manager (winget)...
    winget install --id Python.Python.3.11 --exact --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel% equ 0 set "INSTALL_SUCCESS=1"
)

:: If winget not available or failed, download and run official installer via PowerShell
if "!INSTALL_SUCCESS!"=="0" (
    echo [*] Downloading official Python installer from python.org...
    set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    if /i "%PROCESSOR_ARCHITECTURE%"=="x86" (
        if not defined PROCESSOR_ARCHITEW6432 (
            set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9.exe"
        )
    )

    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('!PY_URL!', '%TEMP%\speedflasher_py_setup.exe')"
    
    if exist "%TEMP%\speedflasher_py_setup.exe" (
        echo [*] Installing Python (silent mode, including pip and tkinter)...
        start /wait "" "%TEMP%\speedflasher_py_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1 Include_launcher=1 Shortcuts=0
        del /f /q "%TEMP%\speedflasher_py_setup.exe" >nul 2>nul
    ) else (
        echo [!] Failed to download Python installer. Check internet connection.
    )
)

:: Re-scan for the newly installed Python
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "FOUND_PYTHON=%%D\python.exe"
            goto :PythonFound
        )
    )
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "FOUND_PYTHON=py -3"
        goto :PythonFound
    )
)

echo.
echo [Error] Python could not be installed automatically.
echo Please install Python 3 manually from https://www.python.org/downloads/
echo Make sure to check 'Add Python to PATH' during installation.
exit /b 1

:PythonFound
echo [*] Python detected: !FOUND_PYTHON!

if "!FOUND_PYTHON!"=="py -3" (
    set "RUN_PY=py -3"
) else (
    set "RUN_PY="!FOUND_PYTHON!""
)

:: 5. Verify pip and requirements
echo [*] Checking dependencies from requirements.txt...
!RUN_PY! -c "import zstandard" >nul 2>nul
if errorlevel 1 (
    echo [*] Installing required packages from requirements.txt...
    !RUN_PY! -m ensurepip --default-pip >nul 2>nul
    !RUN_PY! -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo [*] Retrying with user-scoped pip installation...
        !RUN_PY! -m pip install --user --disable-pip-version-check -r "%~dp0requirements.txt"
    )
) else (
    echo [*] All requirements already satisfied.
)

echo [*] Setup complete. Ready to run.
echo ========================================================================
echo.

endlocal & set "PYTHON_CMD=%FOUND_PYTHON%"
exit /b 0
