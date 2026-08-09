@echo off
setlocal

rem E10 Zone 1 - AUDITION SET A one-click launcher (Owner machine only).
rem This file is intentionally ASCII-only with CRLF line endings to avoid
rem cmd.exe parsing issues. User-facing Chinese messages live in the .ps1
rem file, which PowerShell handles correctly. This file does not read,
rem store, or forward any credential itself.

cd /d "%~dp0"

where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo PowerShell was not found on this machine. Cannot continue.
    echo Please install Windows PowerShell or PowerShell 7 and try again.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run_Audition_Set_A.ps1"
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%
