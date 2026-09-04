"""Bounded subprocess execution for release-gate tests.

The standard :func:`subprocess.run` timeout path terminates only the process it
started.  Windows PowerShell and Git commonly create descendants that retain
captured pipes or continue a worktree operation after the parent is gone.  A
release-gate timeout must terminate the task-owned process tree before raising
so the caller's normal fixture/finally cleanup can run.
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Any


def _terminate_process_tree(pid: int) -> None:
    """Terminate only the process tree rooted at ``pid``."""

    if os.name == "nt":
        killer = subprocess.Popen(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            killer.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            killer.kill()
            killer.communicate()
        return

    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_bounded(*popenargs: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Run a child with a process-tree timeout and ``subprocess.run`` parity.

    The release tests use this only for locally created child processes.  It
    preserves ``capture_output``, ``input``, ``check``, text/encoding options,
    and the normal ``CompletedProcess``/``TimeoutExpired`` behavior.
    """

    timeout = kwargs.pop("timeout", None)
    check = kwargs.pop("check", False)
    capture_output = kwargs.pop("capture_output", False)
    input_value = kwargs.pop("input", None)

    if capture_output:
        if "stdout" in kwargs or "stderr" in kwargs:
            raise ValueError("stdout and stderr arguments may not be used with capture_output")
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if input_value is not None:
        if "stdin" in kwargs:
            raise ValueError("stdin and input arguments may not both be used")
        kwargs["stdin"] = subprocess.PIPE

    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs.setdefault("start_new_session", True)

    process = subprocess.Popen(*popenargs, **kwargs)
    try:
        stdout, stderr = process.communicate(input=input_value, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process.pid)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            process.args,
            timeout,
            output=stdout if stdout is not None else exc.output,
            stderr=stderr if stderr is not None else exc.stderr,
        ) from exc

    result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    if check and result.returncode:
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result
