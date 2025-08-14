@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: Orlando Toolkit - Installer & Updater
:: Single-file batch that:
::  - Stores files under %LOCALAPPDATA%\OrlandoToolkit
::  - Retrieves latest source via curl+zip only (no Git required)
::  - Uses portable WinPython (no system Python required)
::  - Installs dependencies, builds with PyInstaller (quiet), logs to file
::  - Copies a timestamped EXE into releases

title Orlando Toolkit Installer

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
rem Simplified policy: always use main (override via BRANCH=... if needed)
set "BRANCH=%BRANCH%"
if not defined BRANCH set "BRANCH=main"
set "REF_TYPE=heads"
set "ZIP_URL=https://codeload.github.com/%REPO_OWNER%/%REPO_NAME%/zip/refs/%REF_TYPE%/%BRANCH%"
set "VERSION_URL=https://raw.githubusercontent.com/%REPO_OWNER%/%REPO_NAME%/%BRANCH%/VERSION"

:: WinPython portable (includes tkinter)
set "WPCODE=5.0.20221030final"
set "WPFILENAME=Winpython64-3.10.8.0dot.exe"
set "WPDL_URL=https://github.com/winpython/winpython/releases/download/%WPCODE%/%WPFILENAME%"

:: ---------------------------------------------------------------------------------
:: Welcome splash (minimal logo)
:: ---------------------------------------------------------------------------------
call :ShowSplash
echo.

:: ---------------------------------------------------------------------------------
:: Preflight: ensure dirs, logging, and determine action (Install/Update/Up-to-date)
:: ---------------------------------------------------------------------------------
for %%D in ("%VENDOR_DIR%" "%SRC_DIR%" "%APP_DIR%" "%TOOLS_DIR%" "%LOGS_DIR%") do if not exist %%~D mkdir %%~D

:: Prepare timestamp and log file now (prefer PowerShell, fallback to WMIC/date)
set "STAMP="
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" 2^>nul') do set "STAMP=%%I"
if not defined STAMP (
  set "LDT="
  for /f "skip=1 tokens=1" %%I in ('wmic os get localdatetime ^| findstr /r "^[0-9]" 2^>nul') do (
    set "LDT=%%I"
    goto :GotTSFallback0
  )
  :GotTSFallback0
  if defined LDT (
    set "STAMP=%LDT:~0,8%-%LDT:~8,6%"
  ) else (
    set "STAMP=%date:~-4%%date:~3,2%%date:~0,2%-%time:~0,2%%time:~3,2%%time:~6,2%"
    set "STAMP=%STAMP: =0%"
  )
)
set "LOG_FILE=%LOGS_DIR%\deploy-%STAMP%.log"
call :Log "START - Orlando Toolkit installer launched"
call :Log "Config: BRANCH=%BRANCH%, VENDOR_DIR=%VENDOR_DIR%, SRC_DIR=%SRC_DIR%, APP_DIR=%APP_DIR%, TOOLS_DIR=%TOOLS_DIR%"

:: Compute installed and remote versions
set "INSTALLED_VERSION="
if exist "%APP_DIR%\version.txt" for /f "usebackq delims=" %%V in ("%APP_DIR%\version.txt") do set "INSTALLED_VERSION=%%V"
set "REMOTE_VERSION="
rem Fetch remote VERSION (inline) from selected branch
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%" >nul 2>&1
del /f /q "%TOOLS_DIR%\remote_version.txt" >nul 2>&1
curl -fSL -sS -o "%TOOLS_DIR%\remote_version.txt" "%VERSION_URL%" >> "%LOG_FILE%" 2>&1
if not exist "%TOOLS_DIR%\remote_version.txt" (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%VERSION_URL%' -OutFile '%TOOLS_DIR%\\remote_version.txt' } catch { exit 1 }" >> "%LOG_FILE%" 2>&1
)
if exist "%TOOLS_DIR%\remote_version.txt" for /f "usebackq delims=" %%V in ("%TOOLS_DIR%\remote_version.txt") do set "REMOTE_VERSION=%%V"
if not defined REMOTE_VERSION call :Log "WARN - Could not read REMOTE_VERSION from %VERSION_URL%"

set "INSTALLED_PRINT=none"
if defined INSTALLED_VERSION set "INSTALLED_PRINT=%INSTALLED_VERSION%"
set "REMOTE_PRINT=unknown"
if defined REMOTE_VERSION set "REMOTE_PRINT=%REMOTE_VERSION%"
set "PROPOSED_ACTION=INSTALL"
if defined INSTALLED_VERSION if defined REMOTE_VERSION if /I "%INSTALLED_VERSION%"=="%REMOTE_VERSION%" set "PROPOSED_ACTION=SKIP"
if defined INSTALLED_VERSION if defined REMOTE_VERSION if /I not "%INSTALLED_VERSION%"=="%REMOTE_VERSION%" set "PROPOSED_ACTION=UPDATE"
if defined INSTALLED_VERSION if not defined REMOTE_VERSION set "PROPOSED_ACTION=UPDATE"
call :ShowSummary

if /I "%PROPOSED_ACTION%"=="SKIP" (
  choice /c YN /n /m " Already up-to-date. Reinstall anyway? [Y/N]: "
  if errorlevel 2 goto :SuccessNoBuild
  echo   Proceeding with forced reinstall...
  set "FORCE_REINSTALL=1"
) else (
  choice /c YN /n /m " Proceed with %PROPOSED_ACTION%? [Y/N]: "
  if errorlevel 2 goto :UserCancelled
)

rem Directories and logging already initialized above

:: ---------------------------------------------------------------------------------
:: Fetch latest source via curl+zip
:: ---------------------------------------------------------------------------------
call :ProgressUpdate 1 5 "Checking for latest version"

:FetchViaZip
call :ProgressDetail "Downloading latest source..."
set "ZIP_PATH=%TOOLS_DIR%\repo.zip"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>&1

:: Purge source folder before update/install as requested
if exist "%SRC_DIR%" rmdir /s /q "%SRC_DIR%" >nul 2>&1
mkdir "%SRC_DIR%" >nul 2>&1

call :DownloadZip
if errorlevel 1 goto :Fail

call :ProgressDetail "Extracting source..."
call :ExtractZip
if errorlevel 1 goto :Fail

call :MoveExtracted
if errorlevel 1 goto :Fail

call :ProgressDetail "Source prepared"

rem Log extracted top-level folders to help diagnose archive layout
dir /b /ad "%SRC_DIR%" >> "%LOG_FILE%" 2>&1

if not defined SRC_ROOT set "SRC_ROOT=%SRC_DIR%\orlando-toolkit\"
if not exist "%SRC_ROOT%build_exe.py" if not exist "%SRC_ROOT%run.py" if not exist "%SRC_ROOT%orlando_toolkit\app.py" (
  call :LocateSourceRoot
  if errorlevel 1 goto :Fail
)

:AfterFetch
call :ProgressUpdate 2 5 "Preparing Python environment"

set "PYTHON_CMD="
call :SetupPortablePython
if %errorlevel% neq 0 goto :Fail

:: Ensure pip available (some minimal dists may lack it)
"%PYTHON_CMD%" -m ensurepip --default-pip >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  call :Log "INFO - ensurepip failed, falling back to get-pip.py"
  curl -fSL -o "%TOOLS_DIR%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py" >> "%LOG_FILE%" 2>&1
  if exist "%TOOLS_DIR%\get-pip.py" (
    "%PYTHON_CMD%" "%TOOLS_DIR%\get-pip.py" --quiet --no-warn-script-location >> "%LOG_FILE%" 2>&1
    del "%TOOLS_DIR%\get-pip.py" >nul 2>&1
  )
)

call :ProgressUpdate 3 5 "Preparing build environment"

"%PYTHON_CMD%" -c "import PyInstaller" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  call :Log "INFO - PyInstaller not found; installing"
  "%PYTHON_CMD%" -m pip install --quiet --no-cache-dir --disable-pip-version-check --no-warn-script-location pyinstaller >> "%LOG_FILE%" 2>&1
  if %errorlevel% gtr 1 goto :Fail
)

if exist "%SRC_ROOT%requirements.txt" (
  call :Log "INFO - Installing requirements.txt"
  "%PYTHON_CMD%" -m pip install --quiet --no-cache-dir --disable-pip-version-check -r "%SRC_ROOT%requirements.txt" --no-warn-script-location >> "%LOG_FILE%" 2>&1
  if %errorlevel% gtr 1 goto :Fail
) else (
echo     No requirements.txt found under %SRC_ROOT% - skipping dependency install >> "%LOG_FILE%"
)

rem Validate PyInstaller health; repair or reset WinPython if corrupted
call :CheckPyInstallerHealth
if %errorlevel% neq 0 goto :Fail

call :ProgressUpdate 4 5 "Building executable"
pushd "%SRC_ROOT%" >nul 2>&1
echo     Using inline PyInstaller build... >> "%LOG_FILE%"
set "ICON_PATH=%SRC_ROOT%assets\app_icon.ico"
set "ADD_DATA1=%SRC_ROOT%assets;assets"
set "ADD_DATA2=%SRC_ROOT%orlando_toolkit\config;orlando_toolkit/config"

:: Decide entry script (prefer run.py, fallback to orlando_toolkit\app.py)
set "ENTRY_SCRIPT=run.py"
if not exist "%SRC_ROOT%run.py" if exist "%SRC_ROOT%orlando_toolkit\app.py" set "ENTRY_SCRIPT=orlando_toolkit\app.py"

:: If version_info.txt exists, pass it to PyInstaller so EXE properties match
if exist "%SRC_ROOT%version_info.txt" (
  "%PYTHON_CMD%" -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name OrlandoToolkit ^
    --clean ^
    --noconfirm ^
    --icon "%ICON_PATH%" ^
    --add-data="%ADD_DATA1%" ^
    --add-data="%ADD_DATA2%" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.filedialog ^
    --hidden-import tkinter.messagebox ^
    --hidden-import tkinter.scrolledtext ^
    --hidden-import tkinter.font ^
    --hidden-import tkinter.constants ^
    --version-file "%SRC_ROOT%version_info.txt" ^
    "%ENTRY_SCRIPT%" >> "%LOG_FILE%" 2>&1
) else (
  "%PYTHON_CMD%" -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name OrlandoToolkit ^
    --clean ^
    --noconfirm ^
    --icon "%ICON_PATH%" ^
    --add-data="%ADD_DATA1%" ^
    --add-data="%ADD_DATA2%" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.filedialog ^
    --hidden-import tkinter.messagebox ^
    --hidden-import tkinter.scrolledtext ^
    --hidden-import tkinter.font ^
    --hidden-import tkinter.constants ^
    "%ENTRY_SCRIPT%" >> "%LOG_FILE%" 2>&1
)
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
  call :Log "WARN  - Copy failed (possibly in-use). Attempting to stop running app and retry."
  taskkill /IM "OrlandoToolkit.exe" /F >nul 2>&1
  powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
  copy /y "%SOURCE_EXE%" "%TARGET_EXE%" >nul
  if %errorlevel% neq 0 (
    echo     ERROR: Failed to copy executable to App directory
    call :Log "ERROR - Copy to App failed after retry: %SOURCE_EXE% -> %TARGET_EXE%"
    goto :Fail
  ) else (
    call :Log "INFO  - Copy to App succeeded after stopping running instance"
  )
)

:: Write installed version marker for future update checks
if defined REMOTE_VERSION echo %REMOTE_VERSION%> "%APP_DIR%\version.txt"

:: Append an update line to the application's own log
set "APP_LOG_DIR=%APP_DIR%\logs"
if not exist "%APP_LOG_DIR%" mkdir "%APP_LOG_DIR%" >nul 2>&1
set "APP_LOG_FILE=%APP_LOG_DIR%\app.log"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd HH:mm:ss" 2^>nul') do set "NOW=%%I"
if defined NOW (
  if defined INSTALLED_VERSION (
    echo %NOW% - updater - INFO - Updated OrlandoToolkit from %INSTALLED_VERSION% to %REMOTE_VERSION%>> "%APP_LOG_FILE%"
  ) else (
    echo %NOW% - updater - INFO - Installed OrlandoToolkit version %REMOTE_VERSION%>> "%APP_LOG_FILE%"
  )
)

call :ProgressUpdate 5 5 "Cleaning up"

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

cls
echo   +====================================================================+
echo   ^|                            SUCCESS                                 ^|
echo   +====================================================================+
echo     Application ready: %TARGET_EXE%
powershell -NoProfile -Command "try { $WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\Orlando Toolkit.lnk'); $Shortcut.TargetPath = '%TARGET_EXE%'; $Shortcut.WorkingDirectory = (Split-Path -Parent '%TARGET_EXE%'); $Shortcut.Description = 'Orlando Toolkit - DOCX to DITA Converter'; $Shortcut.Save() } catch { exit 1 }"
if not errorlevel 1 echo     Desktop shortcut: created
echo     Log file        : %LOG_FILE%
call :Log "SUCCESS - Installed to %TARGET_EXE%"
echo.
:: Prune old logs (older than 14 days)
forfiles /p "%LOGS_DIR%" /m *.log /d -14 /c "cmd /c del /q @path" >nul 2>&1
if "%CLEAN_TOOLS%"=="1" if exist "%TOOLS_DIR%" rmdir /s /q "%TOOLS_DIR%" >nul 2>&1
echo.
echo   Press any key to close this window...
pause >nul
exit /b 0

:SuccessNoBuild
cls
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
call :ProgressDetail "Setting up portable environment"
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

:: Decide whether to refresh the portable Python
set "_reset_py=0"
if defined FORCE_REINSTALL set "_reset_py=1"
rem Only auto-reset for UPDATE when not being called from health-repair path
if /I "%PROPOSED_ACTION%"=="UPDATE" if /I not "%OT_CALLER%"=="HEALTH" set "_reset_py=1"

if "%_reset_py%"=="1" (
  call :ProgressDetail "Resetting portable environment"
  if defined FORCE_REINSTALL (
    call :Log "INFO - Resetting portable Python (forced reinstall)"
  ) else (
    call :Log "INFO - Resetting portable Python (action %PROPOSED_ACTION%)"
  )
  for /d %%D in ("%TOOLS_DIR%\WPy*") do rmdir /s /q "%%~fD" >nul 2>&1
  rem Keep the SFX if present to avoid a second network download in the same run
)

:: Attempt to locate an existing Python before downloading
set "PYTHON_CMD="
for /d %%D in ("%TOOLS_DIR%\WPy*") do (
  for /d %%P in ("%%~fD\python-*") do (
    if exist "%%~fP\python.exe" set "PYTHON_CMD=%%~fP\python.exe"
  )
)

if defined PYTHON_CMD if "%_reset_py%"=="0" (
  call :ProgressDetail "Reusing existing portable Python"
  goto :EnsurePipTk
)

:: Download and extract WinPython only if needed (avoid double network download in same run)
set "PY_SFX=%TOOLS_DIR%\%WPFILENAME%"
set "WP_SIZE=0"
if exist "%PY_SFX%" for %%A in ("%PY_SFX%") do set "WP_SIZE=%%~zA"
if %WP_SIZE% LSS 20000000 (
  call :ProgressDetail "Downloading portable environment"
  call :DownloadWinPython
  if %errorlevel% neq 0 exit /b 1
)

call :ProgressDetail "Extracting WinPython"
"%PY_SFX%" -y -o"%TOOLS_DIR%" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  echo     ERROR: Extraction of WinPython failed.
  echo     Hint: The downloaded file may be corrupted. Try re-running the script. >> "%LOG_FILE%"
  exit /b 1
)

:: Locate python.exe under tools (prefer WPy*/python-*/python.exe) AFTER extraction
set "PYTHON_CMD="
for /d %%D in ("%TOOLS_DIR%\WPy*") do (
  for /d %%P in ("%%~fD\python-*") do (
    if exist "%%~fP\python.exe" set "PYTHON_CMD=%%~fP\python.exe"
  )
)
if not defined PYTHON_CMD (
  echo     ERROR: python.exe not found after extraction.
  exit /b 1
)

call :Log "PYTHON_CMD selected: %PYTHON_CMD%"

:EnsurePipTk
:: Keep the downloaded SFX during this run to avoid a second download if we must reset
:: It will be cleaned at the end when CLEAN_TOOLS=1 prunes the tools folder

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

call :ProgressDetail "Python ready"
exit /b 0

:: ---------------------------------------------------------------------------------
:CheckPyInstallerHealth
set "_py=%PYTHON_CMD%"
if not defined _py exit /b 1

rem Quick import check
"%_py%" -c "import PyInstaller, sys; sys.exit(0)" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  call :ProgressDetail "Repairing PyInstaller"
  "%_py%" -m pip install --force-reinstall --no-cache-dir --disable-pip-version-check pyinstaller >> "%LOG_FILE%" 2>&1
  call :Log "HEALTH - Reinstalled PyInstaller"
)

"%_py%" -c "import PyInstaller.utils; import PyInstaller.building" >> "%LOG_FILE%" 2>&1
if not errorlevel 1 (
  call :Log "HEALTH - PyInstaller utils/build imports OK"
  exit /b 0
)

rem If still broken, nuke embedded WinPython to force a clean re-extract this run
if defined HEALTH_RESET_DONE (
  call :Log "HEALTH - Already reset once; aborting to prevent loop"
  exit /b 1
)
set "HEALTH_RESET_DONE=1"
call :Log "HEALTH - PyInstaller utils import failed; resetting portable Python"
call :ProgressDetail "Resetting portable Python (corrupted)"
set "_tools=%TOOLS_DIR%"
for /d %%D in ("%_tools%\WPy*") do rmdir /s /q "%%~fD" >nul 2>&1
if exist "%_tools%\python.exe" del /f /q "%_tools%\python.exe" >nul 2>&1

rem Re-extract portable Python now and re-prepare environment within same run without re-downloading
set "OT_CALLER=HEALTH"
call :SetupPortablePython
set "OT_CALLER="
if errorlevel 1 (
  exit /b 1
)

"%PYTHON_CMD%" -m pip install --quiet --no-cache-dir --disable-pip-version-check --no-warn-script-location pyinstaller >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  exit /b 1
)

if exist "%SRC_ROOT%requirements.txt" (
  "%PYTHON_CMD%" -m pip install --quiet --no-cache-dir --disable-pip-version-check -r "%SRC_ROOT%requirements.txt" --no-warn-script-location >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    exit /b 1
  )
)

"%PYTHON_CMD%" -c "import PyInstaller.utils; import PyInstaller.building" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  exit /b 1
) else (
  exit /b 0
)

:: ---------------------------------------------------------------------------------
:Fail
cls
echo   +====================================================================+
echo   ^|                             FAILED                                 ^|
echo   +====================================================================+
echo     Log file: %LOG_FILE%
echo.
echo   Press any key to close this window...
pause >nul
exit /b 1

:UserCancelled
cls
echo   +====================================================================+
echo   ^|                           CANCELLED                                 ^|
echo   +====================================================================+
echo.
echo   Press any key to close this window...
pause >nul
exit /b 0

:: ---------------------------------------------------------------------------------
:DownloadZip
rem Use straight-line flow to avoid parentheses parsing issues
del /f /q "%ZIP_PATH%" >nul 2>&1
call :Log "INFO - Downloading repo zip: %ZIP_URL%"
curl -fSL -o "%ZIP_PATH%" "%ZIP_URL%" >> "%LOG_FILE%" 2>&1
if exist "%ZIP_PATH%" goto :DownloadZipOK
echo     ERROR: Could not download repository zip.
echo     URL: %ZIP_URL%
echo     Retrying via PowerShell... >> "%LOG_FILE%"
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%ZIP_URL%' -OutFile '%ZIP_PATH%' } catch { exit 1 }" >> "%LOG_FILE%" 2>&1
if exist "%ZIP_PATH%" goto :DownloadZipOK
exit /b 1
:DownloadZipOK
exit /b 0

:ExtractZip
where tar >nul 2>&1
if errorlevel 1 goto :UsePS
rem Clean previous extracted folders to avoid confusion
for /d %%D in ("%SRC_DIR%\orlando-toolkit" "%SRC_DIR%\orlando-toolkit-*") do rmdir /s /q "%%~fD" >nul 2>&1
for /d %%D in ("%SRC_DIR%\%REPO_OWNER%-%REPO_NAME%-*") do rmdir /s /q "%%~fD" >nul 2>&1
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-%BRANCH%" "%SRC_DIR%\%REPO_NAME%-main" "%SRC_DIR%\%REPO_NAME%-master") do rmdir /s /q "%%~fD" >nul 2>&1
tar -xf "%ZIP_PATH%" -C "%SRC_DIR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :TarFail
goto :ExtractOk
:UsePS
call :Log "INFO - Using PowerShell Expand-Archive (tar not found)"
rem Clean previous extracted folders to avoid confusion
for /d %%D in ("%SRC_DIR%\orlando-toolkit" "%SRC_DIR%\orlando-toolkit-*") do rmdir /s /q "%%~fD" >nul 2>&1
for /d %%D in ("%SRC_DIR%\%REPO_OWNER%-%REPO_NAME%-*") do rmdir /s /q "%%~fD" >nul 2>&1
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-%BRANCH%" "%SRC_DIR%\%REPO_NAME%-main" "%SRC_DIR%\%REPO_NAME%-master") do rmdir /s /q "%%~fD" >nul 2>&1
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; if (!(Test-Path -LiteralPath '%SRC_DIR%')) { New-Item -ItemType Directory -Path '%SRC_DIR%' | Out-Null }; Expand-Archive -LiteralPath '%ZIP_PATH%' -DestinationPath '%SRC_DIR%' -Force" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :PSFail
goto :ExtractOk
:TarFail
echo     ERROR: Extraction failed with tar
exit /b 1
:PSFail
echo     ERROR: Extraction failed with PowerShell Expand-Archive
call :Log "ERROR - Expand-Archive failed for %ZIP_PATH% -> %SRC_DIR%"
exit /b 1
:ExtractOk
exit /b 0

:MoveExtracted
set "FOUND_DIR="
for /d %%D in ("%SRC_DIR%\orlando-toolkit-*") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\orlando-toolkit") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_OWNER%-%REPO_NAME%-*") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-%BRANCH%") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
if defined CHANNEL for /d %%D in ("%SRC_DIR%\%REPO_NAME%-%CHANNEL%") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-main") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
for /d %%D in ("%SRC_DIR%\%REPO_NAME%-master") do set "FOUND_DIR=%%~fD" & goto :HaveExtractedDir
:HaveExtractedDir
if not defined FOUND_DIR (
  echo     ERROR: Could not locate extracted folder
  call :Log "ERROR - Could not locate extracted folder under %SRC_DIR% after unzip"
  exit /b 1
)

rem Option A: flatten into %SRC_DIR% directly (requested behavior)
rem Move contents of FOUND_DIR up one level, then remove the folder
robocopy "%FOUND_DIR%" "%SRC_DIR%" /E /MOVE /NJH /NJS /NFL /NDL /NP >> "%LOG_FILE%" 2>&1
if errorlevel 4 goto :MoveFailRobocopy2
if exist "%FOUND_DIR%" rmdir /s /q "%FOUND_DIR%" >nul 2>&1
set "SRC_ROOT=%SRC_DIR%\"
exit /b 0

:MoveFailRobocopy2
echo     ERROR: Failed to flatten extracted folder to %SRC_DIR% >> "%LOG_FILE%"
echo     FROM: %FOUND_DIR% >> "%LOG_FILE%"
dir /b /ad "%SRC_DIR%" >> "%LOG_FILE%" 2>&1
exit /b 1

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
powershell -NoProfile -Command "try { $WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%EXE_PATH%'; $Shortcut.WorkingDirectory = (Split-Path -Parent '%EXE_PATH%'); $Shortcut.Description = 'Orlando Toolkit - DOCX to DITA Converter'; $Shortcut.Save() } catch { exit 1 }"
if %errorlevel% neq 0 call :Log "WARN - Could not create desktop shortcut"
exit /b 0


:: ---------------------------------------------------------------------------------
:FetchRemoteVersion
rem Attempt to fetch remote VERSION file from the selected branch
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"
set "REMOTE_VERSION="
del /f /q "%TOOLS_DIR%\remote_version.txt" >nul 2>&1
curl -fSL -o "%TOOLS_DIR%\remote_version.txt" "%VERSION_URL%" >> "%LOG_FILE%" 2>&1
if not exist "%TOOLS_DIR%\remote_version.txt" (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%VERSION_URL%' -OutFile '%TOOLS_DIR%\\remote_version.txt' } catch { exit 1 }" >> "%LOG_FILE%" 2>&1
)
if exist "%TOOLS_DIR%\remote_version.txt" for /f "usebackq delims=" %%V in ("%TOOLS_DIR%\remote_version.txt") do set "REMOTE_VERSION=%%V"
exit /b 0

:: ---------------------------------------------------------------------------------
:ResolveLatestTag
rem Resolve the latest semver-like tag (vX.Y.Z or X.Y.Z) from GitHub API
set "BRANCH="
for /f %%T in ('powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $h=@{ 'User-Agent'='curl' }; $tags = Invoke-RestMethod -Headers $h -Uri 'https://api.github.com/repos/%REPO_OWNER%/%REPO_NAME%/tags'; $tags.name | Sort-Object { $_ -replace '^v','' } -Descending | Select-Object -First 1" 2^>nul') do set "BRANCH=%%T"
if not defined BRANCH exit /b 0
exit /b 0

:: ---------------------------------------------------------------------------------
:DownloadWinPython
rem Robust download with size verification and PowerShell fallback (no parentheses)
set "WP_TRIES=0"
:DLWP_Retry
set /a WP_TRIES=WP_TRIES+1
curl -fSL -o "%PY_SFX%" "%WPDL_URL%" >> "%LOG_FILE%" 2>&1
set "WP_SIZE=0"
for %%A in ("%PY_SFX%") do set "WP_SIZE=%%~zA"
if not exist "%PY_SFX%" set "WP_SIZE=0"
if %WP_SIZE% GEQ 20000000 goto :DLWP_OkCurl

rem Curl result too small; try PowerShell
if exist "%PY_SFX%" del /f /q "%PY_SFX%" >nul 2>&1
powershell -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%WPDL_URL%', '%PY_SFX%')" >> "%LOG_FILE%" 2>&1
set "WP_SIZE=0"
for %%A in ("%PY_SFX%") do set "WP_SIZE=%%~zA"
if %WP_SIZE% GEQ 20000000 goto :DLWP_OkPS

rem Retry once
if %WP_TRIES% LSS 2 goto :DLWP_Retry
echo     ERROR: Could not obtain a valid WinPython package (file too small). >> "%LOG_FILE%"
echo     URL: %WPDL_URL% >> "%LOG_FILE%"
exit /b 1

:DLWP_OkCurl
:DLWP_OkPS
exit /b 0

:: ---------------------------------------------------------------------------------

:: ---------------------------------------------------------------------------------
:ResolveRefType
rem Determine if BRANCH refers to a branch (heads) or tag (tags). Default heads.
set "REF_TYPE=heads"
rem Heuristic: if BRANCH looks like vX or a semantic version, prefer tags
echo %BRANCH% | findstr /r /c:"^v[0-9]" >nul && set "REF_TYPE=tags"
echo %BRANCH% | findstr /r /c:"^[0-9][0-9]*\.[0-9]" >nul && set "REF_TYPE=tags"
rem Validate chosen ref; if invalid, flip type
set "_TESTREF=https://github.com/%REPO_OWNER%/%REPO_NAME%/archive/refs/%REF_TYPE%/%BRANCH%.zip"
curl -fsI "%_TESTREF%" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
  if /I "%REF_TYPE%"=="heads" (
    set "REF_TYPE=tags"
  ) else (
    set "REF_TYPE=heads"
  )
)
exit /b 0

:: ---------------------------------------------------------------------------------
:ProgressUpdate
:: Usage: call :ProgressUpdate <currentStep> <totalSteps> "Label"
set "_OT_CURRENT_STEP=%~1"
set "_OT_TOTAL_STEPS=%~2"
set "_OT_CURRENT_LABEL=%~3"
set "_OT_SUBSTATUS="
call :_OT_ProgressRedraw
exit /b 0

:ProgressDetail
:: Usage: call :ProgressDetail "message"
set "_OT_SUBSTATUS=%~1"
call :_OT_ProgressRedraw
exit /b 0

:RenderProgressBar
:: Usage: call :RenderProgressBar <value> <total> "title"
setlocal EnableDelayedExpansion
set "_val=%~1"
set "_tot=%~2"
if not defined _tot set "_tot=100"
if "!_tot!"=="0" set "_tot=100"
set /a _pct=(_val*100)/_tot
if !_pct! lss 0 set "_pct=0"
if !_pct! gtr 100 set "_pct=100"
set /a _barWidth=40
set /a _filled=(_pct*_barWidth)/100
set /a _empty=_barWidth-_filled
set "_bar="
for /L %%I in (1,1,!_filled!) do set "_bar=!_bar!#"
for /L %%I in (1,1,!_empty!) do set "_bar=!_bar!-"
set "_title=%~3"
echo [!_bar!] !_pct!%% !_title!
endlocal & exit /b 0

:: ---------------------------------------------------------------------------------
:Log
:: Usage: call :Log "message"
setlocal
if not defined LOG_FILE goto :_noLog
>> "%LOG_FILE%" echo %DATE% %TIME% - %~1
:_noLog
endlocal & exit /b 0

:: ---------------------------------------------------------------------------------
:ShowSplash
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
echo   Press Enter to continue...
set /p "_CONT= "
exit /b 0

:: ---------------------------------------------------------------------------------
:ShowSummary
setlocal EnableDelayedExpansion
cls
set "_i=none"
if defined INSTALLED_VERSION set "_i=%INSTALLED_VERSION%"
set "_r=unknown"
if defined REMOTE_VERSION set "_r=%REMOTE_VERSION%"
echo Installed: !_i!
echo Available: !_r!  (branch %BRANCH%)
if defined PROPOSED_ACTION echo Action   : %PROPOSED_ACTION%
endlocal & exit /b 0

:_OT_ProgressRedraw
setlocal EnableDelayedExpansion
cls
call :RenderProgressBar !_OT_CURRENT_STEP! !_OT_TOTAL_STEPS! "Step !_OT_CURRENT_STEP!/!_OT_TOTAL_STEPS! - !_OT_CURRENT_LABEL!"
if defined _OT_SUBSTATUS echo !_OT_SUBSTATUS!
endlocal & exit /b 0

