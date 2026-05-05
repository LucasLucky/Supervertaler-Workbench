# Create Windows Start Menu shortcuts for Supervertaler (Developer Version)
#
# Creates TWO shortcuts pointing at this source tree:
#
#   1. "Supervertaler Workbench (Dev)"               → run.cmd
#      Launches Supervertaler with a console window so you can see all
#      stdout/stderr ([LOG] lines, exceptions, prints) live as they happen.
#      The console stays open after the app closes (`pause` in run.cmd).
#
#   2. "Supervertaler Workbench (Dev, no terminal)"  → pythonw.exe Supervertaler.py
#      Launches Supervertaler under the GUI subsystem. No console window
#      ever flashes. All stdout/stderr is silently swallowed; for
#      diagnostics use Help → Open Diagnostic Log inside the app, which
#      reads %USERPROFILE%\Supervertaler\workbench\logs\supervertaler.log.
#
# Re-run this script after moving the source directory — both shortcuts
# embed absolute paths and need to be regenerated when the tree moves.

$ErrorActionPreference = 'Stop'

# Get the directory where this script is located
$SupervertalerDir = $PSScriptRoot
$RunCmdPath = Join-Path $SupervertalerDir "run.cmd"
$IconPath = Join-Path $SupervertalerDir "assets\icon.ico"
$ScriptPath = Join-Path $SupervertalerDir "Supervertaler.py"

# Verify the source tree looks right
if (!(Test-Path $RunCmdPath)) {
    Write-Host ""
    Write-Host "ERROR: run.cmd not found in $SupervertalerDir" -ForegroundColor Red
    Write-Host "Make sure you're running this script from the Supervertaler source directory." -ForegroundColor Yellow
    Write-Host ""
    $null = Read-Host "Press Enter to exit"
    exit 1
}
if (!(Test-Path $ScriptPath)) {
    Write-Host ""
    Write-Host "ERROR: Supervertaler.py not found in $SupervertalerDir" -ForegroundColor Red
    Write-Host "Make sure you're running this script from the Supervertaler source directory." -ForegroundColor Yellow
    Write-Host ""
    $null = Read-Host "Press Enter to exit"
    exit 1
}

# Find pythonw.exe for the no-terminal variant. Mirrors the resolution
# used by run.cmd / run-silent.cmd: prefer .venv if present, else PATH.
$PythonwPath = $null
$VenvPythonw = Join-Path $SupervertalerDir ".venv\Scripts\pythonw.exe"
if (Test-Path $VenvPythonw) {
    $PythonwPath = $VenvPythonw
} else {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $PythonwPath = $cmd.Source }
}

$StartMenuPath = [Environment]::GetFolderPath("StartMenu")
$WshShell = New-Object -ComObject WScript.Shell

# Clean up legacy dev shortcut names from previous versions of this script.
# Only remove shortcuts whose target matches this source directory — never
# touch a "Supervertaler Workbench.lnk" belonging to an installed end-user build.
$LegacyShortcutNames = @(
    "Supervertaler (Dev).lnk",
    "Supervertaler Workbench.lnk"
)
foreach ($name in $LegacyShortcutNames) {
    $legacyPath = Join-Path $StartMenuPath "Programs\$name"
    if (Test-Path $legacyPath) {
        try { $legacyShortcut = $WshShell.CreateShortcut($legacyPath) }
        catch { $legacyShortcut = $null }
        if ($legacyShortcut -and $legacyShortcut.TargetPath -eq $RunCmdPath) {
            Remove-Item $legacyPath -Force
            Write-Host "Removed legacy shortcut '$name'." -ForegroundColor Yellow
        }
    }
}

# ── Shortcut 1: with terminal (run.cmd) ────────────────────────────────
$TerminalShortcutPath = Join-Path $StartMenuPath "Programs\Supervertaler Workbench (Dev).lnk"
$Shortcut = $WshShell.CreateShortcut($TerminalShortcutPath)
$Shortcut.TargetPath       = $RunCmdPath
$Shortcut.WorkingDirectory = $SupervertalerDir
$Shortcut.Description      = "Supervertaler - AI Translation Tool (Dev build, with terminal for live logs)"
if (Test-Path $IconPath) { $Shortcut.IconLocation = $IconPath }
$Shortcut.Save()
Write-Host ("Created: " + $TerminalShortcutPath) -ForegroundColor Green

# ── Shortcut 2: no terminal (pythonw.exe Supervertaler.py) ─────────────
# Targeting pythonw.exe directly (instead of run-silent.cmd) avoids the
# brief cmd-window flash that happens when a .cmd is launched from a
# shortcut, even with `start /b` inside.
if ($PythonwPath) {
    $SilentShortcutPath = Join-Path $StartMenuPath "Programs\Supervertaler Workbench (Dev, no terminal).lnk"
    $Shortcut = $WshShell.CreateShortcut($SilentShortcutPath)
    $Shortcut.TargetPath       = $PythonwPath
    $Shortcut.Arguments        = '"' + $ScriptPath + '"'
    $Shortcut.WorkingDirectory = $SupervertalerDir
    $Shortcut.Description      = "Supervertaler - AI Translation Tool (Dev build, no terminal — quiet launch)"
    if (Test-Path $IconPath) { $Shortcut.IconLocation = $IconPath }
    $Shortcut.Save()
    Write-Host ("Created: " + $SilentShortcutPath) -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "WARNING: Couldn't find pythonw.exe (neither in .venv\Scripts\ nor on PATH)." -ForegroundColor Yellow
    Write-Host "Skipping the 'no terminal' shortcut. Install Python (with the launcher" -ForegroundColor Yellow
    Write-Host "option that adds it to PATH) or create a .venv\ in this folder, then re-run." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host ""
Write-Host "Both dev shortcuts live in your Start Menu — type 'Supervertaler' to find them." -ForegroundColor Cyan
Write-Host "Right-click either to pin it to the taskbar." -ForegroundColor Cyan
Write-Host ""
$null = Read-Host "Press Enter to close"
