@echo off
setlocal enabledelayedexpansion

echo ========================================================================
echo                         SpeedFlasher Setup
echo ========================================================================

:: Check if extracted properly
if not exist "%~dp0main.py" (
    echo.
    echo ========================================================================
    echo [Error] Files are missing or you are running directly from inside a ZIP.
    echo Please EXTRACT the entire SpeedFlasher folder before running!
    echo ========================================================================
    echo.
    pause
    exit /b 1
)

set "FOUND_PYTHON="

:: 1. Check Python in PATH (skip Microsoft WindowsApps store stub)
where python >nul 2>nul
if errorlevel 1 goto :CheckPyLauncher
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

:CheckPyLauncher
:: 2. Check Python Launcher 'py -3'
where py >nul 2>nul
if errorlevel 1 goto :CheckFolders
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "FOUND_PYTHON=py -3"
    goto :PythonFound
)

:CheckFolders
:: 3. Scan known installation locations
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "FOUND_PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe" & goto :VerifyCandidate
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "FOUND_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe" & goto :VerifyCandidate
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "FOUND_PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :VerifyCandidate
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "FOUND_PYTHON=%LOCALAPPDATA%\Programs\Python\Python310\python.exe" & goto :VerifyCandidate
if exist "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"  set "FOUND_PYTHON=%LOCALAPPDATA%\Programs\Python\Python39\python.exe"  & goto :VerifyCandidate
if exist "%LOCALAPPDATA%\Programs\Python\Python38\python.exe"  set "FOUND_PYTHON=%LOCALAPPDATA%\Programs\Python\Python38\python.exe"  & goto :VerifyCandidate

if exist "%ProgramFiles%\Python313\python.exe" set "FOUND_PYTHON=%ProgramFiles%\Python313\python.exe" & goto :VerifyCandidate
if exist "%ProgramFiles%\Python312\python.exe" set "FOUND_PYTHON=%ProgramFiles%\Python312\python.exe" & goto :VerifyCandidate
if exist "%ProgramFiles%\Python311\python.exe" set "FOUND_PYTHON=%ProgramFiles%\Python311\python.exe" & goto :VerifyCandidate
if exist "%ProgramFiles%\Python310\python.exe" set "FOUND_PYTHON=%ProgramFiles%\Python310\python.exe" & goto :VerifyCandidate
if exist "%ProgramFiles%\Python39\python.exe"  set "FOUND_PYTHON=%ProgramFiles%\Python39\python.exe"  & goto :VerifyCandidate
if exist "%ProgramFiles%\Python38\python.exe"  set "FOUND_PYTHON=%ProgramFiles%\Python38\python.exe"  & goto :VerifyCandidate

if exist "C:\Python312\python.exe" set "FOUND_PYTHON=C:\Python312\python.exe" & goto :VerifyCandidate
if exist "C:\Python311\python.exe" set "FOUND_PYTHON=C:\Python311\python.exe" & goto :VerifyCandidate
if exist "C:\Python310\python.exe" set "FOUND_PYTHON=C:\Python310\python.exe" & goto :VerifyCandidate

goto :InstallPython

:VerifyCandidate
if defined FOUND_PYTHON (
    "%FOUND_PYTHON%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if not errorlevel 1 goto :PythonFound
    set "FOUND_PYTHON="
)

:InstallPython
echo [*] Python was not found on your system.
echo [*] Downloading and configuring Python 3.11 automatically...
echo [*] Please wait a moment while the installer runs...
echo.

set "PY_INSTALLER=%TEMP%\speedflasher_py_setup.exe"
if exist "!PY_INSTALLER!" del /f /q "!PY_INSTALLER!" >nul 2>nul

set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" (
    if not defined PROCESSOR_ARCHITEW6432 (
        set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9.exe"
    )
)

:: Try downloading with curl first (built into Windows 10/11)
where curl.exe >nul 2>nul
if not errorlevel 1 (
    echo [*] Downloading Python using curl...
    curl.exe -L -k -s -o "!PY_INSTALLER!" "!PY_URL!"
)

:: Fallback to PowerShell if curl failed or is missing
if not exist "!PY_INSTALLER!" (
    echo [*] Downloading Python using PowerShell...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('!PY_URL!', '!PY_INSTALLER!')"
)

if not exist "!PY_INSTALLER!" (
    echo [!] Failed to download Python installer automatically.
    goto :InstallFailed
)

echo [*] Installing Python (silent mode, with pip and tcl/tk)...
start /wait "" "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1 Include_launcher=1 Shortcuts=0
del /f /q "!PY_INSTALLER!" >nul 2>nul

:: Re-check user install folder
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "FOUND_PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :PythonFound
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "FOUND_PYTHON=%%D\python.exe"
        goto :PythonFound
    )
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "FOUND_PYTHON=py -3"
        goto :PythonFound
    )
)

:InstallFailed
echo.
echo ========================================================================
echo [Error] Python could not be installed automatically.
echo Please install Python 3.8+ manually from:
echo https://www.python.org/downloads/
echo.
echo Make sure to check "Add Python to PATH" during installation!
echo ========================================================================
echo.
pause
exit /b 1

:PythonFound
echo [*] Python runtime: !FOUND_PYTHON!

if "!FOUND_PYTHON!"=="py -3" (
    set "RUN_PY=py -3"
) else (
    set "RUN_PY="!FOUND_PYTHON!""
)

:: 5. Verify pip and requirements.txt
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
