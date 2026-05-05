@echo off
REM ============================================================
REM Add Supervertaler to your Windows Start Menu
REM ============================================================
REM
REM Double-click this file to add a Start Menu shortcut for
REM Supervertaler Workbench. You can then launch the app from the
REM Start Menu (Win key, type "Supervertaler"), pin it to the
REM taskbar, and so on.
REM
REM This is a friendly wrapper around create_start_menu_shortcut.ps1
REM that bypasses Windows' default PowerShell ExecutionPolicy
REM without changing any system-wide settings.
REM ============================================================

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_start_menu_shortcut.ps1"
if errorlevel 1 (
    echo.
    echo Something went wrong. See the messages above.
    pause
)
