@echo off
:: Build script for Orlando Toolkit Windows executable
:: Run this from the project root directory

echo =========================================
echo    Orlando Toolkit - Windows Build
echo =========================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    pause
    exit /b 1
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