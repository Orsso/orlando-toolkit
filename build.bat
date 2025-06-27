@echo off
:: Build script for Orlando Toolkit Windows executable
:: Run this from the project root directory

echo =========================================
echo    Orlando Toolkit - Windows Build
echo =========================================
echo.

:: Check if Python is available -----------------------------------------------------------------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not detected. Attempting silent install via winget…

    :: Ensure winget is available
    winget --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo Error: winget CLI not found. Please install Python 3.13 manually then re-run this script.
        pause
        exit /b 1
    )

    :: Install latest stable Python 3.13 from Microsoft Store repository
    echo Installing Python 3.13… this may take a few minutes.
    winget install --id "Python.Python.3.13" -e --silent --accept-package-agreements --accept-source-agreements

    if %errorlevel% neq 0 (
        echo Error: winget failed to install Python. Please install it manually.
        pause
        exit /b 1
    )

    :: Refresh PATH for current session
    set "PATH=%PATH%;%LOCALAPPDATA%\\Microsoft\\WindowsApps"

    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo Error: Python still not found after installation. Open a new terminal and try again.
        pause
        exit /b 1
    )
)

:: Check if PyInstaller is available
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
    if %errorlevel% neq 0 (
        echo Error: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

echo Building executable...
echo.

:: Run the build script
python build_exe.py

if %errorlevel% equ 0 (
    echo.
    echo =========================================
    echo    Build completed successfully!
    echo =========================================
    echo.
    echo Your executable is ready in the 'release' folder
    echo.
    pause
) else (
    echo.
    echo =========================================
    echo    Build failed!
    echo =========================================
    echo.
    pause
) 