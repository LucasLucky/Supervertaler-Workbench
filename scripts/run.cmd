@echo off
REM Supervertaler Quick Launch Script
REM Double-click to run Supervertaler with terminal window visible.
REM Lives in scripts/ — cd up to the source root before launching so
REM Supervertaler.py finds modules/, assets/, user_data/ etc. relative
REM to the right CWD.

cd /d "%~dp0.."

echo ========================================
echo   Supervertaler - AI-enhanced CAT tool
echo ========================================
echo.
echo Starting Supervertaler...
echo.

python Supervertaler.py

echo.
echo ========================================
echo   Supervertaler has closed
echo ========================================
echo.
pause
