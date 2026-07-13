@echo off
REM RELEASE-FIX-A3-STATIC-DEPLOY-FIX3 test fixture: simulates a real GNU tar
REM binary (correctly identifies itself as "GNU tar" on --version) that does
REM NOT actually support one of the deterministic-archive flags this Sprint
REM requires -- proving Resolve-GnuTarExecutable's real archive-build smoke
REM test (not just a --version string check) is what gates acceptance.
if "%~1"=="--version" (
  echo tar ^(GNU tar^) 1.20
  echo Copyright ^(C^) fake test fixture
  exit /b 0
)
echo fake-gnu-tar: --sort=name is not supported by this fixture build 1>&2
exit /b 2
