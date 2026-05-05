@echo off
REM Supervertaler Silent Launch Script
REM Double-click to run Supervertaler WITHOUT a terminal window.
REM
REM Uses pythonw.exe (the Windows GUI variant of Python) which runs the
REM app under the GUI subsystem, so no console window is created at all –
REM the cmd window that briefly opens to execute this .cmd exits
REM immediately via `start /b`, leaving only the Qt window on screen.
REM
REM Lives in scripts/ – cd up to the source root before launching so
REM Supervertaler.py finds modules/, assets/, user_data/ etc.
REM
REM All startup output and errors are written to the diagnostic log:
REM   %USERPROFILE%\Supervertaler\workbench\logs\supervertaler.log
REM and can be opened from inside the app via:
REM   Help > Open Diagnostic Log
REM
REM For live debugging, use run.cmd instead – it keeps the terminal open
REM so stdout/stderr (all [LOG] lines) are visible AS they happen.

cd /d "%~dp0.."
start "" /b pythonw Supervertaler.py
