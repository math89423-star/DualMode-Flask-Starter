@echo off
chcp 65001 >nul 2>&1
title DualMode Flask Starter - Build EXE

echo ========================================
echo   DualMode Flask Starter - Windows EXE Builder
echo ========================================
echo.

:: ========== Install PyInstaller if missing ==========
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

:: ========== Build EXE ==========
echo.
echo Building EXE...
pyinstaller DualModeStarter.spec --noconfirm --clean

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed. Check the error messages above.
    pause
    exit /b 1
)

:: ========== Copy .env ==========
if exist ".env.desktop.example" (
    copy /Y .env.desktop.example dist\DualModeStarter\.env >nul
    echo [OK] Copied .env.desktop.example to dist\DualModeStarter\.env
) else (
    echo [INFO] No .env.desktop.example found.
)

echo.
echo ========================================
echo   Build complete!
echo   Output: dist\DualModeStarter\
echo   Usage:
echo     1. Edit dist\DualModeStarter\.env
echo     2. Double-click dist\DualModeStarter\DualModeStarter.exe
echo ========================================
pause
