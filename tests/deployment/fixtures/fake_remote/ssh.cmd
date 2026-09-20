@echo off
REM A017 fixture ssh -- TEST-ONLY. A protocol-level simulator of the remote host that
REM deploy-static-release.ps1 talks to; it never connects anywhere. See fake_remote.py.
REM deploy-static-release.ps1 -UseFixtureTransport only honours a non-production layout
REM when ssh/scp resolve to fixtures like this one under <repo>\tests.
if not defined FAKE_REMOTE_PYTHON set FAKE_REMOTE_PYTHON=python
"%FAKE_REMOTE_PYTHON%" "%~dp0fake_remote.py" ssh %*
exit /b %ERRORLEVEL%
