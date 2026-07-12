@echo off
REM Fake ssh executable for RELEASE-FIX-A2-STATIC-DEPLOY-FIX1 tests -- never
REM connects anywhere. Behavior selected via FAKE_SSH_MODE so a single test
REM fixture can simulate hang/fail/success without touching a real host.
if "%FAKE_SSH_MODE%"=="hang" (
  ping -n 1 127.0.0.1 >nul
  ping -t 127.0.0.1 >nul
  exit /b 1
)
if "%FAKE_SSH_MODE%"=="fail" (
  echo fake ssh: simulated remote command failure 1>&2
  exit /b 1
)
echo fake ssh: ok
exit /b 0
