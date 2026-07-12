@echo off
REM Fake scp executable for RELEASE-FIX-A2-STATIC-DEPLOY-FIX1 tests -- never
REM connects anywhere. Behavior selected via FAKE_SCP_MODE.
if "%FAKE_SCP_MODE%"=="fail" (
  echo fake scp: simulated upload failure 1>&2
  exit /b 1
)
if "%FAKE_SCP_MODE%"=="hang" (
  ping -t 127.0.0.1 >nul
  exit /b 1
)
echo fake scp: ok
exit /b 0
