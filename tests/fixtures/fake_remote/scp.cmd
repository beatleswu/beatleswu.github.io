@echo off
REM A017 fixture scp -- TEST-ONLY. See ssh.cmd and fake_remote.py.
if not defined FAKE_REMOTE_PYTHON set FAKE_REMOTE_PYTHON=python
"%FAKE_REMOTE_PYTHON%" "%~dp0fake_remote.py" scp %*
exit /b %ERRORLEVEL%
