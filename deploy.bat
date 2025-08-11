@echo off
setlocal EnableExtensions

:: Orlando Toolkit - Installer & Updater
:: Single-file batch that:
::  - Stores files under %LOCALAPPDATA%\OrlandoToolkit
::  - Retrieves latest source via curl+zip only (no Git required)
::  - Uses portable WinPython (no system Python required)
::  - Installs dependencies, builds with PyInstaller (quiet), logs to file
::  - Copies a timestamped EXE into releases

title Orlando Toolkit Deployment

:: ---------------------------------------------------------------------------------
:: Configuration
:: ---------------------------------------------------------------------------------
set "APP_NAME=OrlandoToolkit"
rem Simpler behavior: always fetch stable branch (master, then main)
set "VENDOR_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "SRC_DIR=%VENDOR_DIR%\Source"
set "APP_DIR=%VENDOR_DIR%\App"
set "TOOLS_DIR=%VENDOR_DIR%\tools"
set "LOGS_DIR=%VENDOR_DIR%\Logs"
set "CLEAN_TOOLS=1"  

:: Keep Python from writing .pyc/__pycache__ and reduce pip noise
set "PYTHONDONTWRITEBYTECODE=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_PYTHON_VERSION_WARNING=1"

set "REPO_URL=https://github.com/Orsso/orlando-toolkit"
set "REPO_OWNER=Orsso"
set "REPO_NAME=orlando-toolkit"
set "ZIP_URL_STATIC=https://github.com/Orsso/orlando-toolkit/archive/refs/heads/1.1.zip"
set "BRANCH=1.1"

:: WinPython portable (includes tkinter)
set "WPCODE=5.0.20221030final"
set "WPFILENAME=Winpython64-3.10.8.0dot.exe"
set "WPDL_URL=https://github.com/winpython/winpython/releases/download/%WPCODE%/%WPFILENAME%"

:: ---------------------------------------------------------------------------------
:: Banner (reusing ASCII art)
:: ---------------------------------------------------------------------------------
cls
echo(
echo                                   ***               
echo                                 +++++++             
echo                                *+++++++*            
echo                                 +++++++             
echo                         ++++++**+++++++**++++++     
echo                         *++++++++++*++++++++++*     
echo                          +++++*#########*+++++      
echo                          ++++####o   o####+++       
echo                     ++++++++###o  --   o###++++++++ 
echo                    +++++++++###  -----  ###+++++++++
echo                    *++++++++###   ---   ###++++++++*
echo                      **  +++*###       ###*+++  **  
echo                          +++++###########+++++      
echo                          +++++++#######++++++       
echo                         ++++++++++***+++++++++*     
echo                          +++++++*     *+++++++      
echo                             ++++*     *++++         
echo                                 *     *             
echo(
echo                      O R L A N D O  T O O L K I T   
echo                          Installer ^& Updater        
echo(
echo   +-- OVERVIEW ---------------------------------------------------------------+
echo   ^|                                                                          ^|
echo   ^| This script will install or update Orlando Toolkit.           ^|
echo   ^| It downloads the latest code, prepares Python, builds the EXE,           ^|
echo   ^| and stores everything under your user profile.                           ^|
echo   +--------------------------------------------------------------------------+
echo(
echo     Source   : %SRC_DIR%
echo     App      : %APP_DIR%
echo     Tools    : %TOOLS_DIR%
echo     Logs     : %LOGS_DIR%
echo(

:: ---------------------------------------------------------------------------------
:: Confirmation prompt before starting
:: ---------------------------------------------------------------------------------
echo   Press Y to start, or N to cancel.
choice /c YN /n /m " Start now? [Y/N]: "
if errorlevel 2 goto :UserCancelled

:: ---------------------------------------------------------------------------------
:: Ensure directories
:: ---------------------------------------------------------------------------------
for %%D in ("%VENDOR_DIR%" "%SRC_DIR%" "%APP_DIR%" "%TOOLS_DIR%" "%LOGS_DIR%") do if not exist %%~D mkdir %%~D

:: Prepare timestamp and log file now (prefer PowerShell, fallback to WMIC/date)
set "STAMP="
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" 2^>nul') do set "STAMP=%%I"
if not defined STAMP (
  set "LDT="
  for /f "skip=1 tokens=1" %%I in ('wmic os get localdatetime ^| findstr /r "^[0-9]" 2^>nul') do (
    set "LDT=%%I"
    goto :GotTSFallback
  )
  :GotTSFallback
  if defined LDT (
    set "STAMP=%LDT:~0,8%-%LDT:~8,6%"
  ) else (
    set "STAMP=%date:~-4%%date:~3,2%%date:~0,2%-%time:~0,2%%time:~3,2%%time:~6,2%"
    set "STAMP=%STAMP: =0%"
  )
)
set "LOG_FILE=%LOGS_DIR%\deploy-%STAMP%.log"
echo   Logging to: %LOG_FILE%

:: ---------------------------------------------------------------------------------
:: Fetch latest source via curl+zip
:: ---------------------------------------------------------------------------------
echo [1/5] Checking for latest version...

:FetchViaZip
echo     Downloading latest source...
set "ZIP_PATH=%TOOLS_DIR%\repo.zip"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>&1

call :DownloadZip
if errorlevel 1 goto :Fail

echo     Extracting...
call :ExtractZip
if errorlevel 1 goto :Fail

call :MoveExtracted
if errorlevel 1 goto :Fail

rem Log extracted top-level folders to help diagnose archive layout
dir /b /ad "%SRC_DIR%" >> "%LOG_FILE%" 2>&1

if not defined SRC_ROOT set "SRC_ROOT=%SRC_DIR%\orlando-toolkit\"
if not exist "%SRC_ROOT%build_exe.py" (
  call :LocateSourceRoot
  if errorlevel 1 goto :Fail
)

:AfterFetch
echo [2/5] Preparing Python environment...

set "PYTHON_CMD="
call :SetupPortablePython
if %errorlevel% neq 0 goto :Fail

:: Ensure pip available (some minimal dists may lack it)
"%PYTHON_CMD%" -m ensurepip --default-pip >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  curl -fSL -o "%TOOLS_DIR%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py" >> "%LOG_FILE%" 2>&1
  if exist "%TOOLS_DIR%\get-pip.py" (
    "%PYTHON_CMD%" "%TOOLS_DIR%\get-pip.py" --quiet --no-warn-script-location >> "%LOG_FILE%" 2>&1
    del "%TOOLS_DIR%\get-pip.py" >nul 2>&1
  )
)

echo [3/5] Installing build tools...

"%PYTHON_CMD%" -c "import PyInstaller" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  "%PYTHON_CMD%" -m pip install --quiet --no-cache-dir --disable-pip-version-check --no-warn-script-location pyinstaller >> "%LOG_FILE%" 2>&1
  if %errorlevel% gtr 1 goto :Fail
)

if exist "%SRC_ROOT%requirements.txt" (
  "%PYTHON_CMD%" -m pip install --quiet --no-cache-dir --disable-pip-version-check -r "%SRC_ROOT%requirements.txt" --no-warn-script-location >> "%LOG_FILE%" 2>&1
  if %errorlevel% gtr 1 goto :Fail
) else (
  echo     No requirements.txt found under %SRC_ROOT% - skipping dependency install >> "%LOG_FILE%"
)

echo [4/5] Building executable (this may take a while)...
pushd "%SRC_ROOT%" >nul 2>&1
echo     Using inline PyInstaller build... >> "%LOG_FILE%"
set "ICON_PATH=%SRC_ROOT%assets\app_icon.ico"
set "ADD_DATA1=%SRC_ROOT%assets;assets"
set "ADD_DATA2=%SRC_ROOT%orlando_toolkit\config;orlando_toolkit/config"
"%PYTHON_CMD%" -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name OrlandoToolkit ^
  --clean ^
  --noconfirm ^
  --icon "%ICON_PATH%" ^
  --add-data "%ADD_DATA1%" ^
  --add-data "%ADD_DATA2%" ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox ^
  --hidden-import tkinter.scrolledtext ^
  --hidden-import tkinter.font ^
  --hidden-import tkinter.constants ^
  run.py >> "%LOG_FILE%" 2>&1
set "BUILD_STATUS=%errorlevel%"
popd >nul 2>&1
if not "%BUILD_STATUS%"=="0" goto :Fail

:: Verify and copy release exe
set "SOURCE_EXE=%SRC_ROOT%dist\OrlandoToolkit.exe"
if not exist "%SOURCE_EXE%" (
  echo     ERROR: Build did not produce OrlandoToolkit.exe in dist folder
  goto :Fail
)

:: Create App directory and copy exe there
if not exist "%APP_DIR%" mkdir "%APP_DIR%"
set "TARGET_EXE=%APP_DIR%\OrlandoToolkit.exe"
copy /y "%SOURCE_EXE%" "%TARGET_EXE%" >nul
if %errorlevel% neq 0 (
  echo     ERROR: Failed to copy executable to App directory
  goto :Fail
)

echo [5/5] Finalizing...

:: Remove build artifacts to minimize footprint (after successful copy)
if exist "%SRC_ROOT%dist" rmdir /s /q "%SRC_ROOT%dist" >nul 2>&1
if exist "%SRC_ROOT%build" rmdir /s /q "%SRC_ROOT%build" >nul 2>&1
del /f /q "%SRC_ROOT%*.spec" >nul 2>&1
for /d /r "%SRC_ROOT%" %%D in (.) do (
  if /i "%%~nD"=="__pycache__" rmdir /s /q "%%~fD" >nul 2>&1
)
rem Keep source tree in installation folder (no deletion)

:: Remove temporary download files
del /f /q "%TOOLS_DIR%\repo.zip" >nul 2>&1
del /f /q "%TOOLS_DIR%\headers.txt" >nul 2>&1
if "%CLEAN_TOOLS%"=="1" if exist "%TOOLS_DIR%" rmdir /s /q "%TOOLS_DIR%" >nul 2>&1

echo.
echo   +====================================================================+
echo   ^|                            SUCCESS                                 ^|
echo   +====================================================================+
echo     Application ready: %TARGET_EXE%
echo     Creating desktop shortcut...
call :CreateShortcut "%TARGET_EXE%"
echo     Log file        : %LOG_FILE%
echo.
:: Prune old logs (older than 14 days)
forfiles /p "%LOGS_DIR%" /m *.log /d -14 /c "cmd /c del /q @path" >nul 2>&1
if "%CLEAN_TOOLS%"=="1" if exist "%TOOLS_DIR%" rmdir /s /q "%TOOLS_DIR%" >nul 2>&1
echo.
echo   Press any key to close this window...
pause >nul
exit /b 0

:SuccessNoBuild
echo.
echo   +====================================================================+
echo   ^|                            UP-TO-DATE                              ^|
echo   +====================================================================+
echo     The latest version is already installed.
echo     App folder: %APP_DIR%
echo     Log file       : %LOG_FILE%
echo.
:: Clean transient tools
del /f /q "%TOOLS_DIR%\headers.txt" >nul 2>&1
if "%CLEAN_TOOLS%"=="1" if exist "%TOOLS_DIR%" rmdir /s /q "%TOOLS_DIR%" >nul 2>&1
:: Prune old logs (older than 14 days)
forfiles /p "%LOGS_DIR%" /m *.log /d -14 /c "cmd /c del /q @path" >nul 2>&1
echo.
echo   Press any key to close this window...
pause >nul
exit /b 0

:: ---------------------------------------------------------------------------------
:: Functions
:: ---------------------------------------------------------------------------------
:SetupPortablePython
echo     Setting up portable Python...
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

:: Reuse existing WinPython if present
set "PYTHON_CMD="
for /d %%D in ("%TOOLS_DIR%\WPy*") do (
  for /d %%P in ("%%~fD\python-*") do (
    if exist "%%~fP\python.exe" (
      set "PYTHON_CMD=%%~fP\python.exe"
      echo     Using cached Python
      goto :EnsurePipTk
    )
  )
)

:: Download and extract only if not already available
set "PY_SFX=%TOOLS_DIR%\%WPFILENAME%"
if not exist "%PY_SFX%" (
  echo     Downloading WinPython portable...
  curl -fSL -o "%PY_SFX%" "%WPDL_URL%" >> "%LOG_FILE%" 2>&1
  if not exist "%PY_SFX%" (
    echo     ERROR: Could not download WinPython portable.
    exit /b 1
  )
)

echo     Extracting WinPython...
"%PY_SFX%" -y -o"%TOOLS_DIR%" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  echo     ERROR: Extraction of WinPython failed.
  exit /b 1
)

:: Locate python.exe under tools (prefer WPy*/python-*/python.exe)
for /d %%D in ("%TOOLS_DIR%\WPy*") do (
  for /d %%P in ("%%~fD\python-*") do (
    if exist "%%~fP\python.exe" (
      set "PYTHON_CMD=%%~fP\python.exe"
      goto :EnsurePipTk
    )
  )
)
for /r "%TOOLS_DIR%" %%F in (python.exe) do (
  set "PYTHON_CMD=%%~fF"
  goto :EnsurePipTk
)
if not defined PYTHON_CMD (
  echo     ERROR: python.exe not found after extraction.
  exit /b 1
)

:EnsurePipTk
:: Delete the downloaded SFX to save space (only if exists)
if exist "%PY_SFX%" del /f /q "%PY_SFX%" >nul 2>&1

:: Ensure pip and tkinter
"%PYTHON_CMD%" -m ensurepip --default-pip >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  curl -fSL -o "%TOOLS_DIR%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py" >> "%LOG_FILE%" 2>&1
  if exist "%TOOLS_DIR%\get-pip.py" (
    "%PYTHON_CMD%" "%TOOLS_DIR%\get-pip.py" --quiet --no-warn-script-location >> "%LOG_FILE%" 2>&1
    del "%TOOLS_DIR%\get-pip.py" >nul 2>&1
  )
)

"%PYTHON_CMD%" -c "import tkinter" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  echo     ERROR: Portable Python lacks tkinter. Please install a Python with tkinter.
  exit /b 1
)

echo     Python ready
exit /b 0

:: ---------------------------------------------------------------------------------
:Fail
echo.
echo   +====================================================================+
echo   ^|                             FAILED                                 ^|
echo   +====================================================================+
echo     See messages above. Details in: %LOG_FILE%
echo.
echo.
echo   Press any key to close this window...
pause >nul
exit /b 1

:UserCancelled
echo.
echo   +====================================================================+
echo   ^|                           CANCELLED                                 ^|
echo   +====================================================================+
echo     Operation cancelled by user. No changes were made.
echo.
echo   Press any key to close this window...
pause >nul
exit /b 0

:: ---------------------------------------------------------------------------------
:DownloadZip
rem Use straight-line flow to avoid parentheses parsing issues
del /f /q "%ZIP_PATH%" >nul 2>&1
curl -fSL -o "%ZIP_PATH%" "%ZIP_URL_STATIC%" >> "%LOG_FILE%" 2>&1
if exist "%ZIP_PATH%" goto :DownloadZipOK
echo     ERROR: Could not download repository zip.
echo     URL: %ZIP_URL_STATIC%
exit /b 1
:DownloadZipOK
exit /b 0

:ExtractZip
where tar >nul 2>&1
if errorlevel 1 goto :UsePS
if exist "%SRC_DIR%\orlando-toolkit" rmdir /s /q "%SRC_DIR%\orlando-toolkit" >nul 2>&1
tar -xf "%ZIP_PATH%" -C "%SRC_DIR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :TarFail
goto :ExtractOk
:UsePS
echo     Using PowerShell to extract - tar not found
if exist "%SRC_DIR%\orlando-toolkit" rmdir /s /q "%SRC_DIR%\orlando-toolkit" >nul 2>&1
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%ZIP_PATH%' -DestinationPath '%SRC_DIR%' -Force" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :PSFail
goto :ExtractOk
:TarFail
echo     ERROR: Extraction failed with tar
exit /b 1
:PSFail
echo     ERROR: Extraction failed with PowerShell Expand-Archive
exit /b 1
:ExtractOk
exit /b 0

:MoveExtracted
set "FOUND_DIR="
for /d %%D in ("%SRC_DIR%\orlando-toolkit-1.1") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\orlando-toolkit") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_OWNER%-%REPO_NAME%-*") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-%BRANCH%") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
if defined CHANNEL for /d %%D in ("%SRC_DIR%\%REPO_NAME%-%CHANNEL%") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-main") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-master") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
:HaveExtractedDir
if not defined FOUND_DIR (
  echo     ERROR: Could not locate extracted folder
  exit /b 1
)
set "DEST_DIR=%SRC_DIR%\orlando-toolkit"
if /I "%FOUND_DIR%"=="%DEST_DIR%" (
  rem Already normalized; do not self-move
  set "SRC_ROOT=%DEST_DIR%\"
  exit /b 0
)
if exist "%DEST_DIR%" rmdir /s /q "%DEST_DIR%" >nul 2>&1
rem Try simple move first
move /y "%FOUND_DIR%" "%DEST_DIR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  rem If simple move fails, attempt rename within parent, else robocopy fallback
  for %%P in ("%FOUND_DIR%") do (
    set "FOUND_PARENT=%%~dpP"
    set "FOUND_NAME=%%~nxP"
  )
  if /I "%FOUND_PARENT%"=="%SRC_DIR%\" (
    pushd "%SRC_DIR%" >nul 2>&1
    ren "%FOUND_NAME%" "orlando-toolkit" >> "%LOG_FILE%" 2>&1
    popd >nul 2>&1
    if exist "%DEST_DIR%" (
      set "SRC_ROOT=%DEST_DIR%\"
      exit /b 0
    )
  )
  rem Robocopy fallback (0-3 are success codes)
  mkdir "%DEST_DIR%" >nul 2>&1
  robocopy "%FOUND_DIR%" "%DEST_DIR%" /E /MOVE >> "%LOG_FILE%" 2>&1
  if errorlevel 4 goto :MoveFailRobocopy
  rmdir /s /q "%FOUND_DIR%" >nul 2>&1
  set "SRC_ROOT=%DEST_DIR%\"
  exit /b 0
  :MoveFailRobocopy
  echo     ERROR: Failed to move extracted folder to normalized path >> "%LOG_FILE%"
  echo     FROM: %FOUND_DIR% >> "%LOG_FILE%"
  echo     TO  : %DEST_DIR% >> "%LOG_FILE%"
  dir /b /ad "%SRC_DIR%" >> "%LOG_FILE%" 2>&1
  exit /b 1
)
set "SRC_ROOT=%DEST_DIR%\"
exit /b 0

:LocateSourceRoot
set "SRC_ROOT=%SRC_DIR%\orlando-toolkit\"
if exist "%SRC_ROOT%build_exe.py" exit /b 0
if exist "%SRC_ROOT%run.py" exit /b 0
for /r "%SRC_DIR%" %%F in (build_exe.py) do set "SRC_ROOT=%%~dpF" & goto :HaveRoot
for /r "%SRC_DIR%" %%F in (run.py) do set "SRC_ROOT=%%~dpF" & goto :HaveRoot
for /d %%D in ("%SRC_DIR%\%REPO_OWNER%-%REPO_NAME%-*") do set "SRC_ROOT=%%~fD\" & goto :HaveRoot
set "SRC_ROOT=%SRC_DIR%\%REPO_NAME%-%BRANCH%\"
if exist "%SRC_ROOT%build_exe.py" exit /b 0
if exist "%SRC_ROOT%run.py" exit /b 0
set "SRC_ROOT=%SRC_DIR%\%REPO_NAME%-main\"
if exist "%SRC_ROOT%build_exe.py" exit /b 0
if exist "%SRC_ROOT%run.py" exit /b 0
set "SRC_ROOT=%SRC_DIR%\%REPO_NAME%-master\"
if exist "%SRC_ROOT%build_exe.py" exit /b 0
if exist "%SRC_ROOT%run.py" exit /b 0
for /r "%SRC_DIR%" %%F in (requirements.txt) do set "SRC_ROOT=%%~dpF" & goto :HaveRoot
:HaveRoot
if exist "%SRC_ROOT%build_exe.py" exit /b 0
if exist "%SRC_ROOT%run.py" exit /b 0
echo     ERROR: Could not locate source root (missing build_exe.py/run.py) under %SRC_DIR%
exit /b 1

:: ---------------------------------------------------------------------------------
:CreateShortcut
set "EXE_PATH=%~1"
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP_DIR%\Orlando Toolkit.lnk"
powershell -NoProfile -Command "try { $WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%EXE_PATH%'; $Shortcut.WorkingDirectory = (Split-Path -Parent '%EXE_PATH%'); $Shortcut.Description = 'Orlando Toolkit - DOCX to DITA Converter'; $Shortcut.Save(); Write-Host '     Desktop shortcut created successfully' } catch { Write-Host '     Warning: Could not create desktop shortcut' }"
exit /b 0


