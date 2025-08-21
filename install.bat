@echo off
setlocal EnableExtensions

rem =====================
rem Orlando Toolkit - Minimal Installer (runtime ZIP)
rem =====================

rem ---- Config ----
set "APP_NAME=OrlandoToolkit"
set "REPO_OWNER=Orsso"
set "REPO_NAME=orlando-toolkit"
set "ZIP_BASENAME=OrlandoToolkit-AppRuntime-win64"
set "SILENT=%SILENT%"

rem Paths
set "VENDOR_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "LOGS_DIR=%VENDOR_DIR%\Logs"
set "TOOLS_DIR=%VENDOR_DIR%\tools"
set "RUNTIME_DIR=%VENDOR_DIR%\AppRuntime"
set "STAGING_DIR=%VENDOR_DIR%\AppRuntime_new"

rem ---- Prepare dirs ----
if not exist "%VENDOR_DIR%" mkdir "%VENDOR_DIR%" >nul 2>&1
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%" >nul 2>&1
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%" >nul 2>&1

rem ---- Timestamp & log ----
set "STAMP="
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" 2^>nul') do set "STAMP=%%I"
if not defined STAMP set "STAMP=%RANDOM%"
set "LOG_FILE=%LOGS_DIR%\deploy-%STAMP%.log"
call :log "START - Minimal installer"

rem ---- Detect installed version ----
set "INSTALLED_VERSION="
if exist "%RUNTIME_DIR%\app\version.txt" for /f "usebackq delims=" %%V in ("%RUNTIME_DIR%\app\version.txt") do set "INSTALLED_VERSION=%%V"

rem ---- Resolve version (env or auto or prompt) ----
set "VERSION=%VERSION%"
if defined VERSION goto :have_version
call :AutoDetectVersion
if defined VERSION goto :have_version
if "%SILENT%"=="1" goto :need_version_fail
echo Enter version to install (format X.Y.Z), or leave empty to cancel:
set /p VERSION=
if not defined VERSION goto :user_cancelled

:have_version
rem Basic format check X.Y.Z
echo %VERSION%| findstr /r /c:"^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul
if not errorlevel 1 goto :version_ok
echo ERROR: Invalid version format. Expected X.Y.Z
call :log "ERROR - Invalid VERSION format: %VERSION%"
goto :fail

:version_ok
rem ---- Plan action ----
set "PROPOSED_ACTION=INSTALL"
if defined INSTALLED_VERSION set "PROPOSED_ACTION=UPDATE"
if defined INSTALLED_VERSION if /I "%INSTALLED_VERSION%"=="%VERSION%" set "PROPOSED_ACTION=SKIP"
echo.
echo Installed: %INSTALLED_VERSION%
echo Target   : %VERSION%
echo Action   : %PROPOSED_ACTION%

if "%PROPOSED_ACTION%"=="SKIP" goto :maybe_skip
if "%SILENT%"=="1" goto :proceed_download
  choice /c YN /n /m " Proceed with %PROPOSED_ACTION%? [Y/N]: "
if errorlevel 2 goto :user_cancelled

goto :proceed_download

:maybe_skip
if "%SILENT%"=="1" goto :success_skip
choice /c YN /n /m " Already up-to-date. Reinstall anyway? [Y/N]: "
if errorlevel 2 goto :success_skip

:proceed_download
set "TAG=v%VERSION%"
set "ZIP_NAME=%ZIP_BASENAME%-%TAG%.zip"
set "ZIP_URL=https://github.com/%REPO_OWNER%/%REPO_NAME%/releases/download/%TAG%/%ZIP_NAME%"
set "ZIP_PATH=%TOOLS_DIR%\bundle.zip"

echo [1/5] Downloading %ZIP_NAME%
call :log "INFO - Downloading %ZIP_URL%"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>&1
curl -fSL -o "%ZIP_PATH%" "%ZIP_URL%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :download_fail

echo [2/5] Extracting archive
call :log "INFO - Extracting (prefer tar)"
if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%" >nul 2>&1
mkdir "%STAGING_DIR%" >nul 2>&1

where tar >nul 2>&1
if errorlevel 1 goto :extract_ps
 tar -xf "%ZIP_PATH%" -C "%STAGING_DIR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :extract_ps
goto :after_extract

:extract_ps
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%ZIP_PATH%' -DestinationPath '%STAGING_DIR%' -Force" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :extract_fail

:after_extract
echo [3/5] Preparing files
call :log "INFO - Listing top-level after extract"
dir /b /ad "%STAGING_DIR%" >> "%LOG_FILE%" 2>&1

rem --- Flatten if single folder root ---
set COUNT=
for /f %%C in ('dir /b /ad "%STAGING_DIR%" ^| find /c /v ""') do set COUNT=%%C
if not "%COUNT%"=="1" goto :swap
for /f "delims=" %%D in ('dir /b /ad "%STAGING_DIR%"') do set FOUND=%STAGING_DIR%\%%D
call :log "INFO - Flattening from %FOUND%"
robocopy "%FOUND%" "%STAGING_DIR%" /E /MOVE /NJH /NJS /NFL /NDL /NP >> "%LOG_FILE%" 2>&1
if errorlevel 8 goto :flatten_fail
if exist "%FOUND%" rmdir /s /q "%FOUND%" >nul 2>&1

:swap
echo [4/5] Installing files
call :log "INFO - Swapping new runtime"
if exist "%VENDOR_DIR%\AppRuntime_old" rmdir /s /q "%VENDOR_DIR%\AppRuntime_old" >nul 2>&1
if exist "%RUNTIME_DIR%" ren "%RUNTIME_DIR%" "AppRuntime_old" >nul 2>&1
pushd "%VENDOR_DIR%" >nul 2>&1
if not exist "AppRuntime_new" goto :swap_fail
ren "AppRuntime_new" "AppRuntime" >nul 2>&1
popd >nul 2>&1
if not exist "%RUNTIME_DIR%" goto :swap_fail

echo [5/5] Creating shortcut
call :log "INFO - Creating desktop shortcut"
set "LAUNCH_TARGET=%VENDOR_DIR%\AppRuntime\runtime\pythonw.exe"
set "LAUNCH_ARGS=%VENDOR_DIR%\AppRuntime\app\run.py"
set "WORK_DIR=%VENDOR_DIR%\AppRuntime\app"
set "ICON_PATH=%VENDOR_DIR%\AppRuntime\app\assets\app_icon.ico"
powershell -NoProfile -Command "try { $w=New-Object -ComObject WScript.Shell; $lnk=$env:USERPROFILE+'\Desktop\Orlando Toolkit.lnk'; $s=$w.CreateShortcut($lnk); $s.TargetPath=$env:LAUNCH_TARGET; $s.Arguments='\"'+$env:LAUNCH_ARGS+'\"'; $s.WorkingDirectory=$env:WORK_DIR; $s.Description='Orlando Toolkit'; if (Test-Path $env:ICON_PATH) { $s.IconLocation=$env:ICON_PATH }; $s.Save() } catch { exit 1 }" >> "%LOG_FILE%" 2>&1

echo All done. Log: %LOG_FILE%
if "%SILENT%"=="1" goto :no_pause_success
echo Press any key to close...
pause >nul
:no_pause_success
exit /b 0

:success_skip
echo Already up to date. Nothing to do.
if "%SILENT%"=="1" goto :no_pause_skip
echo Press any key to close...
pause >nul
:no_pause_skip
exit /b 0

:need_version_fail
echo ERROR: VERSION not provided. Set VERSION=X.Y.Z and rerun.
call :log "ERROR - VERSION not provided in silent mode"
goto :fail

:download_fail
echo ERROR: Download failed
call :log "ERROR - Download failed"
goto :fail

:extract_fail
echo ERROR: Extraction failed
call :log "ERROR - Extraction failed"
goto :fail

:flatten_fail
echo ERROR: Flatten failed
call :log "ERROR - Flatten failed"
goto :fail

:swap_fail
echo ERROR: Install failed
call :log "ERROR - Swap failed"
goto :fail

:fail
echo FAILED. Log: %LOG_FILE%
if "%SILENT%"=="1" goto :no_pause_fail
echo Press any key to close...
pause >nul
:no_pause_fail
exit /b 1

:user_cancelled
echo CANCELLED.
exit /b 0

:AutoDetectVersion
setlocal
set "VERSION_FOUND="
set "HEADERS=%TOOLS_DIR%\latest_headers.txt"
curl -sI -o "%HEADERS%" "https://github.com/%REPO_OWNER%/%REPO_NAME%/releases/latest" >> "%LOG_FILE%" 2>&1
if exist "%HEADERS%" goto :adev_parse
goto :adev_ps

:adev_parse
set "LOC="
for /f "usebackq tokens=1,* delims=:" %%A in ("%HEADERS%") do if /I "%%A"=="Location" set "LOC=%%B"
for /f "tokens=* delims= " %%Z in ("%LOC%") do set "LOC=%%Z"
set "TMP=%LOC%"
set "TAG="
if defined TMP for %%S in (%TMP:/= %) do set "TAG=%%S"
if not defined TAG goto :adev_ps
if /I "%TAG:~0,1%"=="v" set "TAG=%TAG:~1%"
set "VERSION_FOUND=%TAG%"
goto :adev_done

:adev_ps
if defined VERSION_FOUND goto :adev_done
powershell -NoProfile -Command "$u='https://github.com/%REPO_OWNER%/%REPO_NAME%/releases/latest'; try { $r=Invoke-WebRequest -UseBasicParsing -Uri $u -MaximumRedirection 0 -ErrorAction Stop } catch { $r=$_.Exception.Response }; if ($r -and $r.Headers['Location']) { ($r.Headers['Location']).Split('/')[-1] }" > "%TOOLS_DIR%\latest_tag.txt" 2>> "%LOG_FILE%"
if exist "%TOOLS_DIR%\latest_tag.txt" for /f "usebackq delims=" %%T in ("%TOOLS_DIR%\latest_tag.txt") do set "TAG=%%T"
if not defined TAG goto :adev_done
if /I "%TAG:~0,1%"=="v" set "TAG=%TAG:~1%"
set "VERSION_FOUND=%TAG%"

:adev_done
endlocal & set "VERSION=%VERSION_FOUND%" & goto :eof

:log
rem Usage: call :log "message"
setlocal
if not defined LOG_FILE (
  endlocal & goto :eof
)
echo %DATE% %TIME% - %~1>>"%LOG_FILE%"
endlocal & goto :eof

