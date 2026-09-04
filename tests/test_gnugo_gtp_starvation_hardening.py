"""GnuGo GTP process-starvation hardening (INCIDENT-004).

Source incident: GO_ODYSSEY_PRODUCTION_504_POST_RECOVERY_ROOT_CAUSE_ANALYSIS_003.

Production serves every route from a single gevent hub with the stdlib NOT
monkey-patched, so any blocking pipe read, ``Thread.join`` or OS-lock wait taken
on a request greenlet stalls the whole site — including the dependency-free
``/healthz``. These tests pin the three confirmed defects and the invariants
that must replace them:

A. ``_gtp`` looped forever once the engine hit EOF (no reachable exit branch).
B. ``_gtp_with_timeout`` left its worker alive and spinning after a timeout.
C. A stuck GnuGo command starved the gevent hub, so ``/healthz`` timed out.

Every test here is bounded: no test may hang the suite even against the
pre-fix implementation.
"""

import os
import subprocess
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SECRET_KEY", "gnugo-gtp-hardening-test-secret")

import app as app_module  # noqa: E402


# ── bounded fake GTP engine ──────────────────────────────────────────────────

class _FakeStdin:
    def __init__(self, proc):
        self._proc = proc
        self.written = []

    def write(self, data):
        if self._proc.broken_stdin:
            raise BrokenPipeError("fake stdin closed")
        self.written.append(data)
        return len(data)

    def flush(self):
        if self._proc.broken_stdin:
            raise BrokenPipeError("fake stdin closed")

    def close(self):
        self._proc.broken_stdin = True


class _FakeStdout:
    """Bounded stdout. Raises rather than letting a caller spin forever.

    ``BusyLoop`` is the tripwire for defect A: a correct reader stops at the
    first EOF, so it must never consume anywhere near ``max_reads`` lines.
    """

    class BusyLoop(RuntimeError):
        pass

    def __init__(self, proc, max_reads=200):
        self._proc = proc
        self.reads = 0
        self.max_reads = max_reads

    def readline(self):
        self.reads += 1
        if self.reads > self.max_reads:
            raise _FakeStdout.BusyLoop(
                f"readline() called {self.reads} times past EOF - unbounded loop"
            )
        return self._proc._next_line()

    def close(self):
        pass


class FakeGtpProc:
    """Stand-in for ``subprocess.Popen`` covering only what the GTP layer uses."""

    def __init__(self, script=None, block_forever=False, max_reads=200):
        self._script = list(script or [])
        self._block_forever = block_forever
        self._released = threading.Event()
        self.broken_stdin = False
        self.killed = False
        self.terminated = False
        self.waited = False
        self.returncode = None
        self.stdin = _FakeStdin(self)
        self.stdout = _FakeStdout(self, max_reads=max_reads)
        self.stderr = None
        self.blocked = threading.Event()

    def _next_line(self):
        if self._script:
            return self._script.pop(0)
        if self._block_forever and not self._released.is_set():
            self.blocked.set()
            # Mirrors a wedged engine: the reader parks until the process dies.
            self._released.wait(30)
        return b""  # EOF

    # -- Popen surface --
    def kill(self):
        self.killed = True
        self.returncode = -9
        self._released.set()

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self._released.set()

    def wait(self, timeout=None):
        self.waited = True
        self._released.set()
        self.returncode = self.returncode if self.returncode is not None else 0
        return self.returncode

    def poll(self):
        return self.returncode


def _shutdown(proc):
    """Release any parked reader so a test can never wedge the suite."""
    proc.kill()
    channel = getattr(proc, "_gnugo_channel", None)
    if channel is not None:
        channel.close()


# ── A. EOF contract ──────────────────────────────────────────────────────────

def test_gtp_eof_before_any_response_terminates_immediately():
    """Defect A: EOF with no response lines must raise, not spin."""
    proc = FakeGtpProc(script=[])  # readline() returns b'' forever
    try:
        with pytest.raises(app_module.GnuGoUnavailable):
            app_module._gtp(proc, "genmove B", timeout_sec=5)
        assert proc.stdout.reads <= 2, (
            f"reader consumed {proc.stdout.reads} EOF reads; expected to stop at the first"
        )
    finally:
        _shutdown(proc)


def test_gtp_eof_after_partial_response_terminates_immediately():
    """EOF mid-response is still a dead engine, not a completed answer."""
    proc = FakeGtpProc(script=[b"= D4\n"])  # then EOF, never a blank terminator
    try:
        with pytest.raises(app_module.GnuGoUnavailable):
            app_module._gtp(proc, "genmove B", timeout_sec=5)
        assert proc.stdout.reads <= 3
    finally:
        _shutdown(proc)


def test_gtp_normal_response_preserved():
    """Gameplay contract: a normal '= <value>' response still parses."""
    proc = FakeGtpProc(script=[b"= D4\n", b"\n"])
    try:
        assert app_module._gtp(proc, "genmove B", timeout_sec=5) == "D4"
    finally:
        _shutdown(proc)


def test_gtp_empty_success_response_preserved():
    """'=' with no payload (the usual 'play' reply) still returns ''."""
    proc = FakeGtpProc(script=[b"=\n", b"\n"])
    try:
        assert app_module._gtp(proc, "play B D4", timeout_sec=5) == ""
    finally:
        _shutdown(proc)


def test_gtp_error_response_still_returns_none():
    """GTP '?' failure keeps its historical None contract (callers branch on it)."""
    proc = FakeGtpProc(script=[b"? illegal move\n", b"\n"])
    try:
        assert app_module._gtp(proc, "play B D4", timeout_sec=5) is None
    finally:
        _shutdown(proc)


def test_gtp_multiline_response_preserved():
    proc = FakeGtpProc(script=[b"= A1 B2\n", b"C3 D4\n", b"\n"])
    try:
        resp = app_module._gtp(proc, "list_stones black", timeout_sec=5)
        assert "A1 B2" in resp
    finally:
        _shutdown(proc)


def test_gtp_on_dead_engine_fails_fast_without_new_worker():
    """A dead engine must not churn a fresh worker thread per call."""
    proc = FakeGtpProc(script=[b"= D4\n", b"\n"])
    proc.kill()  # engine already exited
    before = threading.active_count()
    try:
        with pytest.raises(app_module.GnuGoUnavailable):
            app_module._gtp(proc, "genmove B", timeout_sec=5)
        assert threading.active_count() <= before, "spawned a worker for a dead engine"
    finally:
        _shutdown(proc)


def test_gtp_broken_stdin_raises_bounded_error():
    proc = FakeGtpProc(script=[b"= D4\n", b"\n"])
    proc.broken_stdin = True
    try:
        with pytest.raises(app_module.GnuGoUnavailable):
            app_module._gtp(proc, "genmove B", timeout_sec=5)
    finally:
        _shutdown(proc)


# ── B. timeout / worker lifecycle ────────────────────────────────────────────

def test_gtp_timeout_raises_timeouterror_subclass():
    """The 504 client contract keys off TimeoutError - it must stay a TimeoutError."""
    proc = FakeGtpProc(block_forever=True)
    try:
        with pytest.raises(TimeoutError):
            app_module._gtp(proc, "genmove B", timeout_sec=1)
    finally:
        _shutdown(proc)


def test_gtp_timeout_kills_and_reaps_process():
    """Defect B(1): a timed-out engine must be killed and reaped, not orphaned."""
    proc = FakeGtpProc(block_forever=True)
    try:
        with pytest.raises(TimeoutError):
            app_module._gtp(proc, "genmove B", timeout_sec=1)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not proc.waited:
            time.sleep(0.02)
        assert proc.killed or proc.terminated, "timed-out engine was never killed"
        assert proc.waited, "timed-out engine was never reaped (zombie)"
    finally:
        _shutdown(proc)


def test_gtp_timeout_worker_does_not_survive():
    """Defect B(2): the worker must exit, not spin forever on a dead pipe."""
    proc = FakeGtpProc(block_forever=True)
    try:
        with pytest.raises(TimeoutError):
            app_module._gtp(proc, "genmove B", timeout_sec=1)
        channel = getattr(proc, "_gnugo_channel", None)
        assert channel is not None
        channel.close()
        assert channel.join(timeout=10), "GTP worker survived the timeout"
    finally:
        _shutdown(proc)


def test_zero_timeout_is_not_unbounded():
    """timeout_sec<=0 used to mean 'no timeout at all'; it must now be bounded."""
    proc = FakeGtpProc(block_forever=True)
    try:
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            app_module._gtp_with_timeout(proc, "genmove B", 0)
        assert time.monotonic() - start < app_module._GNUGO_GTP_DEFAULT_TIMEOUT_SEC + 15
    finally:
        _shutdown(proc)


# ── B(3). repeated-timeout leak regression ───────────────────────────────────

def _settle(deadline_sec=15):
    """Wait for transient reaper/worker threads to retire."""
    end = time.monotonic() + deadline_sec
    baseline = threading.active_count()
    stable = 0
    while time.monotonic() < end:
        time.sleep(0.1)
        now = threading.active_count()
        if now == baseline:
            stable += 1
            if stable >= 3:
                return
        else:
            baseline = now
            stable = 0


@pytest.mark.parametrize("rounds", [20])
def test_repeated_timeouts_leak_no_threads_and_no_zombies(rounds):
    """20 consecutive forced timeouts must leave zero persistent threads."""
    _settle()
    before = threading.active_count()
    procs = []
    for _ in range(rounds):
        proc = FakeGtpProc(block_forever=True)
        procs.append(proc)
        with pytest.raises(TimeoutError):
            app_module._gtp(proc, "genmove B", timeout_sec=1)
        _shutdown(proc)

    _settle()
    after = threading.active_count()
    growth = after - before

    unreaped = [p for p in procs if not p.waited]
    assert not unreaped, f"{len(unreaped)}/{rounds} engines left unreaped (zombies)"
    # One shared reaper thread may be created on first use and then persists.
    assert growth <= 1, (
        f"thread count grew by {growth} across {rounds} timeouts "
        f"({before} -> {after}); expected no persistent per-timeout workers"
    )


# ── C. gevent hub starvation ─────────────────────────────────────────────────

_STUCK_RULE = "/__test__/stuck-gnugo"
_STUCK_STATE = {}


def _stuck_gnugo_route():
    """Test-only route that wedges a GTP command on the serving hub."""
    proc = _STUCK_STATE.get("proc")
    started = _STUCK_STATE.get("started")
    if proc is None:
        return "no-proc", 200
    if started is not None:
        started.set()
    try:
        app_module._gtp(proc, "genmove B", timeout_sec=8)
    except Exception as exc:  # bounded: timeout or unavailable
        return f"gtp-ended:{type(exc).__name__}", 200
    return "gtp-ok", 200


# Flask forbids add_url_rule once the app has served a request, so this must be
# registered at import time, before any server starts.
app_module.app.add_url_rule(_STUCK_RULE, "__test_stuck_gnugo", _stuck_gnugo_route)


@pytest.fixture(scope="module")
def gevent_server():
    """The real app on a real gevent hub, in its own OS thread.

    Clients stay on separate OS threads so the harness itself can never be the
    thing that blocks the hub (in production nginx is a separate process).
    """
    pytest.importorskip("gevent")
    holder = {}

    def _serve():
        from gevent.pywsgi import WSGIServer

        server = WSGIServer(("127.0.0.1", 0), app_module.app, log=None)
        server.start()
        holder["server"] = server
        holder["port"] = server.server_port
        server.serve_forever()

    threading.Thread(target=_serve, daemon=True).start()
    deadline = time.monotonic() + 20
    while "port" not in holder and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "port" in holder, "gevent server never bound"
    yield "http://127.0.0.1:%d" % holder["port"]
    try:
        holder["server"].stop(timeout=5)
    except Exception:
        pass


@pytest.mark.parametrize("probe", ["/healthz", "/api/healthz"])
def test_health_probe_stays_responsive_during_stuck_gnugo(gevent_server, probe):
    """Defect C: a wedged GnuGo command must not starve the gevent hub.

    Runs the real application under a real gevent WSGI server (production's
    serving model, stdlib deliberately NOT monkey-patched) and measures the
    dependency-free health probe while a GTP command is wedged.
    """
    import urllib.request

    base = gevent_server
    proc = FakeGtpProc(block_forever=True)
    started = threading.Event()
    _STUCK_STATE["proc"] = proc
    _STUCK_STATE["started"] = started

    def _get(path, timeout):
        with urllib.request.urlopen(base + path, timeout=timeout) as r:
            return r.status, r.read()

    try:
        threading.Thread(target=lambda: _get(_STUCK_RULE, 30), daemon=True).start()
        assert started.wait(15), "stuck route never started"
        assert proc.blocked.wait(15), "GTP command never reached the blocking read"

        latencies = []
        for _ in range(3):
            t0 = time.monotonic()
            status, _body = _get(probe, 5)
            latencies.append(time.monotonic() - t0)
            assert status == 200
            time.sleep(0.05)

        worst = max(latencies)
        print("%s worst latency during stuck GnuGo: %.1f ms" % (probe, worst * 1000))
        # Must be drastically below the 15/30/60s GnuGo deadlines.
        assert worst < 2.0, (
            "%s took %.2fs during a stuck GnuGo command - hub starved" % (probe, worst)
        )
    finally:
        _shutdown(proc)
        _STUCK_STATE.clear()


# ── request-path blocking-primitive audit ────────────────────────────────────

def test_no_unbounded_gtp_read_on_request_path():
    """Static guard: the blocking reader must never be reachable from a greenlet.

    ``_gtp_read_response`` is the only function permitted to touch the pipe, and
    it must run on a channel worker thread.
    """
    import inspect

    src = inspect.getsource(app_module._gtp)
    assert "stdout.readline" not in src, (
        "_gtp performs a pipe read directly - it must delegate to a worker thread"
    )
    assert "join(" not in src, "_gtp joins a thread on the request path"


def test_per_game_lock_helper_is_non_blocking():
    """The per-game lock must be acquired cooperatively, never with a blocking wait."""
    lock = threading.Lock()
    game = {"lock": lock}
    lock.acquire()  # simulate a concurrent request holding it
    try:
        start = time.monotonic()
        with pytest.raises(app_module.GnuGoBusy):
            with app_module._gnugo_game_lock(game, timeout_sec=1):
                pass
        elapsed = time.monotonic() - start
        assert elapsed < 5, "busy lock wait was not bounded"
    finally:
        lock.release()
