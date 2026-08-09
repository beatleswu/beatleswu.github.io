@echo off
rem E10 Zone 1 - AUDITION SET A one-click launcher (Owner machine only).
rem Double-click this file. It does not read, store, or forward any
rem credential itself -- it only hands off to Run_Audition_Set_A.ps1,
rem which prompts for the ElevenLabs API key securely (masked input,
rem process-only, never written to disk).

setlocal
cd /d "%~dp0"

where powershell >nul 2>&1
if errorlevel 1 (
    echo 找不到 PowerShell，無法執行此工具。
    echo PowerShell was not found on this machine.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run_Audition_Set_A.ps1"
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%
