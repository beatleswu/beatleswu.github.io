@echo off
rem E10 Zone 1 - FINAL LOCKED VOICES full spoken-dialogue launcher (Owner machine only).
rem This file is intentionally ASCII-only with CRLF line endings to avoid
rem cmd.exe parsing issues -- see .gitattributes and
rem tests/test_e10_zone1_audio_launcher_windows_compat.py. User-facing
rem Chinese messages live in the .ps1 file, which PowerShell handles correctly.
rem This file does not read, store, or forward any credential itself.

setlocal

cd /d "%~dp0"

where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo PowerShell was not found on this machine. Cannot continue.
    echo Please install Windows PowerShell or PowerShell 7 and try again.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run_Zone1_Final_Voices.ps1"
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%
