@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: Orlando Toolkit - Installer & Updater (Runtime ZIP)
:: - Downloads a prebuilt runtime bundle ZIP from GitHub Releases
:: - Optional SHA256 verification if .sha256 is published
:: - Extracts to %LOCALAPPDATA%\OrlandoToolkit\AppRuntime_new then atomically swaps to AppRuntime
:: - Creates a desktop shortcut to launch.cmd (no admin required)
:: - Supports interactive and silent modes, robust retries, detailed logs

Title Orlando Toolkit Installer

:: ---------------------------------------------------------------------------------
:: Configuration
:: ---------------------------------------------------------------------------------
set "APP_NAME=OrlandoToolkit"
set "VENDOR_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "APP_RUNTIME_DIR=%VENDOR_DIR%\AppRuntime"
set "APP_RUNTIME_NEW_DIR=%VENDOR_DIR%\AppRuntime_new"
set "LOGS_DIR=%VENDOR_DIR%\Logs"
set "TOOLS_DIR=%VENDOR_DIR%\tools"
set "CLEAN_TOOLS=1"  

:: Mode: SILENT=1 disables prompts and pauses
set "SILENT=%SILENT%"

:: Release source: GitHub Releases (tags)
set "REPO_OWNER=Orsso"
set "REPO_NAME=orlando-toolkit"

:: Release asset naming
set "ZIP_BASENAME=OrlandoToolkit-AppRuntime-win64"
:: If REMOTE_VERSION is X.Y.Z → download vX.Y.Z tag asset: %ZIP_BASENAME%-vX.Y.Z.zip

:: ---------------------------------------------------------------------------------
:: Welcome / Preflight
:: ---------------------------------------------------------------------------------
call :ShowSplash

for %%D in ("%VENDOR_DIR%" "%APP_RUNTIME_DIR%" "%APP_RUNTIME_NEW_DIR%" "%LOGS_DIR%" "%TOOLS_DIR%") do if not exist %%~D mkdir %%~D >nul 2>&1

:: Prepare timestamp and log file
set "STAMP="
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" 2^>nul') do set "STAMP=%%I"
if not defined STAMP set "STAMP=log-%RANDOM%"
set "LOG_FILE=%LOGS_DIR%\deploy-%STAMP%.log"
call :Log "START - Runtime ZIP installer launched"

:: ---------------------------------------------------------------------------------
:: Determine installed and remote versions
:: ---------------------------------------------------------------------------------
set "INSTALLED_VERSION="
if exist "%APP_RUNTIME_DIR%\app\version.txt" for /f "usebackq delims=" %%V in ("%APP_RUNTIME_DIR%\app\version.txt") do set "INSTALLED_VERSION=%%V"

set "REMOTE_VERSION="
if defined VERSION set "REMOTE_VERSION=%VERSION%"
if not defined REMOTE_VERSION call :FetchLatestReleaseVersion

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
  if not "%SILENT%"=="1" (
  choice /c YN /n /m " Already up-to-date. Reinstall anyway? [Y/N]: "
    if errorlevel 2 goto :SuccessNoChange
  echo   Proceeding with forced reinstall...
  set "FORCE_REINSTALL=1"
  ) else (
    goto :SuccessNoChange
  )
) else (
  if not "%SILENT%"=="1" (
  choice /c YN /n /m " Proceed with %PROPOSED_ACTION%? [Y/N]: "
  if errorlevel 2 goto :UserCancelled
)
)

:: ---------------------------------------------------------------------------------
:: Build download URLs and filenames
:: ---------------------------------------------------------------------------------
set "REMOTE_TAG=v%REMOTE_VERSION%"
set "ZIP_FILE_VERSIONED=%ZIP_BASENAME%-%REMOTE_TAG%.zip"
set "ZIP_URL_VERSIONED=https://github.com/%REPO_OWNER%/%REPO_NAME%/releases/download/%REMOTE_TAG%/%ZIP_FILE_VERSIONED%"
set "ZIP_PATH=%TOOLS_DIR%\bundle.zip"
set "SHA_URL_VERSIONED=%ZIP_URL_VERSIONED%.sha256"
set "SHA_PATH=%TOOLS_DIR%\bundle.zip.sha256"

call :ProgressUpdate 1 5 "Downloading runtime bundle"

:: Clean old temp files
if exist "%ZIP_PATH" del /f /q "%ZIP_PATH%" >nul 2>&1
if exist "%SHA_PATH" del /f /q "%SHA_PATH%" >nul 2>&1

:: Download versioned asset (required)
call :DownloadWithRetry "%ZIP_URL_VERSIONED%" "%ZIP_PATH%"
if errorlevel 1 goto :Fail

:: Optional checksum: download .sha256 for the versioned asset
call :DownloadWithRetry "%SHA_URL_VERSIONED%" "%SHA_PATH%"
if not errorlevel 1 (
  call :ProgressDetail "Verifying checksum"
  call :VerifyChecksum "%ZIP_PATH%" "%SHA_PATH%"
  if !errorlevel! neq 0 (
    call :Log "ERROR - Checksum mismatch for %ZIP_PATH%"
    goto :Fail
  )
) else (
  call :Log "INFO - No checksum found; skipping verification"
)

call :ProgressUpdate 2 5 "Extracting bundle"

:: Prepare staging directory
if exist "%APP_RUNTIME_NEW_DIR%" rmdir /s /q "%APP_RUNTIME_NEW_DIR%" >nul 2>&1
mkdir "%APP_RUNTIME_NEW_DIR%" >nul 2>&1

call :ExtractZip "%ZIP_PATH%" "%APP_RUNTIME_NEW_DIR%"
if errorlevel 1 goto :Fail

call :FlattenIfNeeded "%APP_RUNTIME_NEW_DIR%"
if errorlevel 1 goto :Fail

call :ProgressUpdate 3 5 "Switching to new version"

:: Atomic-like swap: AppRuntime -> AppRuntime_old, AppRuntime_new -> AppRuntime
pushd "%VENDOR_DIR%" >nul 2>&1
if exist "AppRuntime_old" rmdir /s /q "AppRuntime_old" >nul 2>&1
if exist "AppRuntime" ren "AppRuntime" "AppRuntime_old" >nul 2>&1
if not exist "AppRuntime_new" (
  popd >nul 2>&1
  call :Log "ERROR - Staging folder missing before swap"
  goto :Fail
)
ren "AppRuntime_new" "AppRuntime" >nul 2>&1
popd >nul 2>&1

:: Best-effort cleanup of old runtime
if exist "%VENDOR_DIR%\AppRuntime_old" rmdir /s /q "%VENDOR_DIR%\AppRuntime_old" >nul 2>&1

call :ProgressUpdate 4 5 "Creating desktop shortcut"

set "LAUNCH_PATH=%APP_RUNTIME_DIR%\launch.cmd"
call :CreateShortcut "%LAUNCH_PATH%"

:: Write installed version marker to app log (if version.txt exists)
set "APP_LOG_DIR=%APP_RUNTIME_DIR%\app\logs"
if not exist "%APP_LOG_DIR%" mkdir "%APP_LOG_DIR%" >nul 2>&1
set "APP_LOG_FILE=%APP_LOG_DIR%\app.log"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd HH:mm:ss" 2^>nul') do set "NOW=%%I"
if exist "%APP_RUNTIME_DIR%\app\version.txt" (
  for /f "usebackq delims=" %%V in ("%APP_RUNTIME_DIR%\app\version.txt") do set "NEWV=%%V"
)
if defined NOW (
  if defined INSTALLED_VERSION (
    echo %NOW% - updater - INFO - Updated OrlandoToolkit from %INSTALLED_VERSION% to %NEWV%>> "%APP_LOG_FILE%"
  ) else (
    echo %NOW% - updater - INFO - Installed OrlandoToolkit version %NEWV%>> "%APP_LOG_FILE%"
  )
)

call :ProgressUpdate 5 5 "Cleaning up"

:: Remove temp tools if requested
if exist "%TOOLS_DIR%\bundle.zip" del /f /q "%TOOLS_DIR%\bundle.zip" >nul 2>&1
if exist "%TOOLS_DIR%\bundle.zip.sha256" del /f /q "%TOOLS_DIR%\bundle.zip.sha256" >nul 2>&1
if "%CLEAN_TOOLS%"=="1" if exist "%TOOLS_DIR%" rmdir /s /q "%TOOLS_DIR%" >nul 2>&1

cls
echo   +====================================================================+
echo   ^|                            SUCCESS                                 ^|
echo   +====================================================================+
if exist "%LAUNCH_PATH%" echo     Application ready: %LAUNCH_PATH%
if exist "%LAUNCH_PATH%" echo     Desktop shortcut: created (if permissions allowed)
echo     Log file        : %LOG_FILE%
call :Log "SUCCESS - Installed runtime to %APP_RUNTIME_DIR%"

echo.
if not "%SILENT%"=="1" (
echo   Press any key to close this window...
pause >nul
)
exit /b 0

:SuccessNoChange
cls
echo   +====================================================================+
echo   ^|                            UP-TO-DATE                              ^|
echo   +====================================================================+
echo     The latest version is already installed.
echo     App folder: %APP_RUNTIME_DIR%
echo     Log file   : %LOG_FILE%
echo.
if not "%SILENT%"=="1" (
echo   Press any key to close this window...
pause >nul
)
exit /b 0

:: ---------------------------------------------------------------------------------
:: Functions
:: ---------------------------------------------------------------------------------
:DownloadWithRetry
:: Usage: call :DownloadWithRetry "<url>" "<dest>"
setlocal EnableDelayedExpansion
set "_url=%~1"
set "_dest=%~2"
set "_tries=0"
set "_max=3"
:dl_loop
set /a _tries+=1
call :Log "INFO - Downloading !_url! (attempt !_tries! of !_max!)"
curl -fSL -o "!_dest!" "!_url!" >> "%LOG_FILE%" 2>&1
if exist "!_dest!" (
  for %%A in ("!_dest!") do if %%~zA gtr 0 (
    endlocal & exit /b 0
  )
)
:: Fallback PowerShell
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -UseBasicParsing -Uri '%~1' -OutFile '%~2' } catch { exit 1 }" >> "%LOG_FILE%" 2>&1
if exist "!_dest!" (
  for %%A in ("!_dest!") do if %%~zA gtr 0 (
    endlocal & exit /b 0
  )
)
if !_tries! lss !_max! (
  powershell -NoProfile -Command "Start-Sleep -Seconds %_tries%" >nul 2>&1
  goto :dl_loop
)
endlocal & exit /b 1

:VerifyChecksum
:: Usage: call :VerifyChecksum "<file>" "<sha256_file>"
setlocal EnableDelayedExpansion
set "_file=%~1"
set "_sha=%~2"
if not exist "!_file!" endlocal & exit /b 1
if not exist "!_sha!" endlocal & exit /b 1
set "_expected="
for /f "usebackq tokens=1" %%H in ("!_sha!") do set "_expected=%%H" & goto :got_expected
:got_expected
if not defined _expected endlocal & exit /b 1
for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath '%~1' -Algorithm SHA256).Hash" 2^>nul') do set "_actual=%%H"
if /I "!_actual!"=="!_expected!" (
  endlocal & exit /b 0
) else (
  endlocal & exit /b 1
)

:ExtractZip
:: Usage: call :ExtractZip "<zip_path>" "<dest_dir>"
setlocal EnableDelayedExpansion
set "_zip=%~1"
set "_dest=%~2"
where tar >nul 2>&1
if errorlevel 1 goto :UsePS
:: Clean destination and extract
powershell -NoProfile -Command "if (!(Test-Path -LiteralPath '%~2')) { New-Item -ItemType Directory -Path '%~2' | Out-Null }" >nul 2>&1
tar -xf "%~1" -C "%~2" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  endlocal & exit /b 1
)
endlocal & exit /b 0
:UsePS
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; if (!(Test-Path -LiteralPath '%~2')) { New-Item -ItemType Directory -Path '%~2' | Out-Null }; Expand-Archive -LiteralPath '%~1' -DestinationPath '%~2' -Force" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  exit /b 1
) else (
  exit /b 0
)

:FlattenIfNeeded
:: Usage: call :FlattenIfNeeded "<dir>"
setlocal EnableDelayedExpansion
set "_root=%~1"
set "_found="
set "_count=0"
for /f "delims=" %%D in ('dir /b /ad "!_root!"') do (
  set /a _count+=1
  set "_found=%%~fD"
)
:: If there is exactly one subdirectory and no files at root, move its contents up
set "_files=0"
for /f %%F in ('dir /b /a-d "!_root!" ^| find /c /v ""') do set "_files=%%F"
if "!_count!"=="1" if "!_files!"=="0" (
  call :Log "INFO - Flattening extracted folder"
  robocopy "!_found!" "!_root!" /E /MOVE /NJH /NJS /NFL /NDL /NP >> "%LOG_FILE%" 2>&1
  if errorlevel 8 (
    endlocal & exit /b 1
  )
  if exist "!_found!" rmdir /s /q "!_found!" >nul 2>&1
)
endlocal & exit /b 0

:FetchRemoteVersion
:: Determine latest release tag from GitHub API (vX.Y.Z → X.Y.Z)
for /f %%T in ('powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $h=@{ 'User-Agent'='curl' }; try { (Invoke-RestMethod -Headers $h -Uri 'https://api.github.com/repos/%REPO_OWNER%/%REPO_NAME%/releases/latest').tag_name } catch { '' }" 2^>nul') do set "_tag=%%T"
if defined _tag (
  set "REMOTE_VERSION=%_tag%"
  if /I "%REMOTE_VERSION:~0,1%"=="v" set "REMOTE_VERSION=%REMOTE_VERSION:~1%"
)
exit /b 0

:FetchLatestReleaseVersion
:: Fallback: ask GitHub API for latest release tag (vX.Y.Z → X.Y.Z)
for /f %%T in ('powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $h=@{ 'User-Agent'='curl' }; try { (Invoke-RestMethod -Headers $h -Uri 'https://api.github.com/repos/%REPO_OWNER%/%REPO_NAME%/releases/latest').tag_name } catch { '' }" 2^>nul') do set "_tag=%%T"
if defined _tag (
  set "REMOTE_VERSION=%_tag%"
  if /I "%REMOTE_VERSION:~0,1%"=="v" set "REMOTE_VERSION=%REMOTE_VERSION:~1%"
)
exit /b 0

:CreateShortcut
:: Usage: call :CreateShortcut "<target_path>"
set "EXE_PATH=%~1"
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP_DIR%\Orlando Toolkit.lnk"
powershell -NoProfile -Command "try { $WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%EXE_PATH%'; $Shortcut.WorkingDirectory = (Split-Path -Parent '%EXE_PATH%'); $Shortcut.Description = 'Orlando Toolkit'; $Shortcut.Save() } catch { exit 1 }" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 call :Log "WARN - Could not create desktop shortcut"
exit /b 0

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

:Log
:: Usage: call :Log "message"
setlocal
if not defined LOG_FILE goto :_noLog
>> "%LOG_FILE%" echo %DATE% %TIME% - %~1
:_noLog
endlocal & exit /b 0

:ShowSplash
if "%SILENT%"=="1" exit /b 0
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

:ShowSummary
setlocal EnableDelayedExpansion
cls
set "_i=none"
if defined INSTALLED_VERSION set "_i=%INSTALLED_VERSION%"
set "_r=unknown"
if defined REMOTE_VERSION set "_r=%REMOTE_VERSION%"
echo Installed: !_i!
echo Available: !_r!
if defined PROPOSED_ACTION echo Action   : %PROPOSED_ACTION%
endlocal & exit /b 0

:_OT_ProgressRedraw
setlocal EnableDelayedExpansion
cls
call :RenderProgressBar !_OT_CURRENT_STEP! !_OT_TOTAL_STEPS! "Step !_OT_CURRENT_STEP!/!_OT_TOTAL_STEPS! - !_OT_CURRENT_LABEL!"
if defined _OT_SUBSTATUS echo !_OT_SUBSTATUS!
endlocal & exit /b 0

:Fail
cls
echo   +====================================================================+
echo   ^|                             FAILED                                 ^|
echo   +====================================================================+
echo     Log file: %LOG_FILE%
echo.
if not "%SILENT%"=="1" (
  echo   Press any key to close this window...
  pause >nul
)
exit /b 1

:UserCancelled
cls
echo   +====================================================================+
echo   ^|                           CANCELLED                                ^|
echo   +====================================================================+
echo.
if not "%SILENT%"=="1" (
  echo   Press any key to close this window...
  pause >nul
)
exit /b 0

