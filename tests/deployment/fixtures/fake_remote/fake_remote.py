"""Protocol-level fixture for the remote host that deploy-static-release.ps1 talks to.

TEST-ONLY. It is what `ssh.cmd` / `scp.cmd` in this directory execute when
deploy-static-release.ps1 runs with -UseFixtureTransport (which the script only
honours when ssh and scp resolve to fixtures under <repo>\\tests). It never opens
a network connection.

It simulates exactly the remote commands the static deploy issues, against a
sandbox directory tree (``$FAKE_REMOTE_DIR/fs``) and a small JSON state file
(``$FAKE_REMOTE_DIR/state.json``), and appends one JSON line per invocation to
``$FAKE_REMOTE_DIR/commands.jsonl`` so a test can assert what was -- and, as
important, what was NOT -- executed, and in which order.

Fidelity choices:
  * scp uploads copy the real local bytes into the sandbox; ``sha256sum``,
    ``tar -xf`` (Python tarfile), ``find | wc -l`` and the batched
    ``sha256sum --check --strict`` script operate on the real sandbox files.
  * The atomic switch command (guard + write) is EXECUTED by a real POSIX
    ``sh`` with shell-function shims for ``cd``/``sudo``/``readlink``/``ln``/``mv``
    bound to the sandbox symlink state, so the compare-and-swap logic that ships
    to Production is the logic under test, not a regex re-implementation of it.
  * Any command shape it does not recognise fails loudly (exit 97) instead of
    silently succeeding.

Scenario knobs live in ``state["scenario"]``:
  corrupt_archive_on_upload  flip one byte inside the first file's data area of
                             the staging archive as it is "uploaded" (the tar
                             still extracts; only its bytes differ)
  hooks                      [{"on": <kind>, "occurrence": n, "set_current": path}]
                             runs after the n-th command of that kind: rewrites
                             the live symlink target, i.e. "another deployer
                             switched it now"
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

STATE_DIR = Path(os.environ["FAKE_REMOTE_DIR"])
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "commands.jsonl"
FS_ROOT = STATE_DIR / "fs"


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def fs_path(remote_path: str) -> Path:
    parts = [p for p in remote_path.split("/") if p]
    if ".." in parts:
        raise ValueError(f"path traversal in fixture path: {remote_path}")
    return FS_ROOT.joinpath(*parts)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log(entry: dict) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def bump(state: dict, kind: str) -> int:
    counters = state.setdefault("counters", {})
    counters[kind] = counters.get(kind, 0) + 1
    return counters[kind]


def run_hooks(state: dict, kind: str, occurrence: int) -> None:
    for hook in state.get("scenario", {}).get("hooks", []):
        if hook.get("on") == kind and int(hook.get("occurrence", 1)) == occurrence:
            if "set_current" in hook:
                state["current"] = hook["set_current"]
                state.setdefault("hook_events", []).append({"on": kind, "occurrence": occurrence, "set_current": hook["set_current"]})


# --- result helper -----------------------------------------------------------

def out(kind: str, code: int = 0, stdout: str = "", stderr: str = ""):
    return kind, code, stdout, stderr


# --- simple single-command handlers -------------------------------------------

def h_exists(state, m):
    return out("exists", 0, "EXISTS\n" if fs_path(m["p"]).exists() else "ABSENT\n")


def h_readlink(state, m):
    n = bump(state, "readlink")
    current = state.get("current") or ""
    result = out("readlink", 0, (current + "\n") if current and m["p"] == state["root"].rstrip("/") + "/current" else "")
    run_hooks(state, "readlink", n)
    return result


def h_sha256sum_file(state, m):
    target = fs_path(m["p"])
    if not target.is_file():
        return out("sha256sum_file", 1, "", f"sha256sum: {m['p']}: No such file or directory\n")
    return out("sha256sum_file", 0, f"{sha256_file(target)}  {m['p']}\n")


def h_tar_extract(state, m):
    n = bump(state, "tar_extract")
    archive, dest = fs_path(m["a"]), fs_path(m["d"])
    if not archive.is_file():
        return out("tar_extract", 2, "", f"tar: {m['a']}: Cannot open: No such file or directory\n")
    if not dest.is_dir():
        return out("tar_extract", 2, "", f"tar: {m['d']}: Cannot chdir: No such file or directory\n")
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    archive.unlink()
    state.setdefault("extractions", []).append({"archive": m["a"], "dest": m["d"]})
    run_hooks(state, "tar_extract", n)
    return out("tar_extract", 0)


def h_find_count(state, m):
    root = fs_path(m["d"])
    return out("find_count", 0, f"{sum(1 for p in root.rglob('*') if p.is_file()) if root.exists() else 0}\n")


def h_find_bytes(state, m):
    root = fs_path(m["d"])
    return out("find_bytes", 0, f"{sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) if root.exists() else 0}\n")


def h_manifest_present(state, m):
    return out("manifest_present", 0, "PRESENT\n" if fs_path(m["p"]).is_file() else "ABSENT\n")


def h_docker_restart(state, m):
    n = bump(state, "docker_restart")
    state.setdefault("restarts", []).append([m["a"], m["b"]])
    state["health"] = state.get("scenario", {}).get("health_after_restart", "healthy")
    run_hooks(state, "docker_restart", n)
    return out("docker_restart", 0, f"{m['a']}\n{m['b']}\n")


def h_docker_inspect_health(state, m):
    return out("docker_inspect_health", 0, state.get("health", "healthy") + "\n")


def h_docker_exec_sha(state, m):
    mount = state["mount_dest"].rstrip("/")
    if not (m["p"] == mount or m["p"].startswith(mount + "/")):
        return out("docker_exec_sha", 1, "", f"sha256sum: {m['p']}: No such file or directory\n")
    relative = m["p"][len(mount):].lstrip("/")
    target = fs_path(state["current"]) / relative
    if not target.is_file():
        return out("docker_exec_sha", 1, "", f"sha256sum: {m['p']}: No such file or directory\n")
    return out("docker_exec_sha", 0, f"{sha256_file(target)}  {m['p']}\n")


# --- the atomic switch: executed by a REAL POSIX sh --------------------------------

def h_switch(state, command):
    """Run the switch command under a real sh; shell-function shims stand in for the
    privileged host commands and keep the symlink in the sandbox state."""
    sh = os.environ.get("FAKE_REMOTE_SH") or "sh"
    work = STATE_DIR / "switch"
    work.mkdir(exist_ok=True)
    current_file, next_file, writes_file = work / "current.txt", work / "next.txt", work / "writes.txt"
    current_file.write_text(state.get("current") or "", encoding="utf-8")
    writes_file.write_text("", encoding="utf-8")
    prelude = "\n".join([
        f"C='{current_file.as_posix()}'; N='{next_file.as_posix()}'; W='{writes_file.as_posix()}'",
        "cd() { :; }",
        'sudo() { "$@"; }',
        'readlink() { cat "$C" 2>/dev/null; }',
        'ln() { echo "ln $*" >> "$W"; printf \'%s\' "$2" > "$N"; }',
        'mv() { echo "mv $*" >> "$W"; cp "$N" "$C"; }',
    ])
    proc = subprocess.run([sh, "-c", prelude + "\n" + command], capture_output=True, text=True)
    writes = [line for line in writes_file.read_text(encoding="utf-8").splitlines() if line]
    if any(line.startswith("mv ") for line in writes):
        state["current"] = current_file.read_text(encoding="utf-8")
    state.setdefault("symlink_writes", []).append({"writes": writes, "exit": proc.returncode, "current_after": state.get("current")})
    n = bump(state, "switch")
    run_hooks(state, "switch", n)
    return out("switch", proc.returncode, proc.stdout, proc.stderr)


# --- `sh -s` scripts -----------------------------------------------------------------

def handle_script(state, script: str):
    text = script.strip("\n")
    m = re.fullmatch(r"mkdir -p((?: '[^']*')+)", text.strip())
    if m:
        for directory in re.findall(r"'([^']*)'", m.group(1)):
            fs_path(directory).mkdir(parents=True, exist_ok=True)
        return out("mkdir_batch", 0)
    m = re.fullmatch(r"cd '(?P<d>[^']*)' && sha256sum --check --strict - <<'(?P<eof>[A-Z0-9_]+)'\n(?P<body>.*)\n(?P=eof)", text, re.S)
    if m:
        base, lines, failed = fs_path(m["d"]), [], 0
        for entry in m["body"].split("\n"):
            expected, _, rel = entry.partition("  ")
            target = base / rel
            if not target.is_file():
                lines.append(f"sha256sum: {rel}: No such file or directory\n{rel}: FAILED open or read")
                failed += 1
            elif sha256_file(target) == expected:
                lines.append(f"{rel}: OK")
            else:
                lines.append(f"{rel}: FAILED")
                failed += 1
        if failed:
            lines.append(f"sha256sum: WARNING: {failed} computed checksum did NOT match")
        return out("batch_sha_verify", 1 if failed else 0, "\n".join(lines) + "\n")
    return out("unhandled_script", 97, "", f"FAKE_REMOTE_UNHANDLED_SCRIPT: {text[:200]!r}\n")


COMMANDS = [
    (re.compile(r"^if \[ -e '(?P<p>[^']*)' \]; then echo EXISTS; else echo ABSENT; fi$"), h_exists),
    (re.compile(r"^readlink -f '(?P<p>[^']*)' 2>/dev/null \|\| true$"), h_readlink),
    (re.compile(r"^sha256sum '(?P<p>[^']*)'$"), h_sha256sum_file),
    (re.compile(r"^tar -xf '(?P<a>[^']*)' -C '(?P<d>[^']*)' && rm -f '(?P=a)'$"), h_tar_extract),
    (re.compile(r"^find '(?P<d>[^']*)' -type f \| wc -l$"), h_find_count),
    (re.compile(r"^find '(?P<d>[^']*)' -type f -exec stat -c%s \{\} \\; \| awk '\{s\+=\$1\} END\{print s\+0\}'$"), h_find_bytes),
    (re.compile(r"^test -f '(?P<p>[^']*)' && echo PRESENT \|\| echo ABSENT$"), h_manifest_present),
    (re.compile(r"^docker restart '(?P<a>[^']*)' '(?P<b>[^']*)'$"), h_docker_restart),
    (re.compile(r"^docker inspect '(?P<n>[^']*)' --format '\{\{\.State\.Health\.Status\}\}'$"), h_docker_inspect_health),
    (re.compile(r"^docker exec '(?P<n>[^']*)' sha256sum '(?P<p>[^']*)'$"), h_docker_exec_sha),
]


def handle_ssh(state, command: str, script: str | None):
    if script is not None:
        return handle_script(state, script)
    for pattern, handler in COMMANDS:
        match = pattern.match(command)
        if match:
            return handler(state, match)
    if command.startswith("cd '") and "sudo ln -sfnT" in command:
        return h_switch(state, command)
    return out("unhandled", 97, "", f"FAKE_REMOTE_UNHANDLED_COMMAND: {command[:300]!r}\n")


def handle_scp(state, local: str, destination: str):
    remote = destination.split(":", 1)[1]
    data = Path(local).read_bytes()
    scenario = state.get("scenario", {})
    corrupted = False
    if scenario.get("corrupt_archive_on_upload") and re.search(r"/\.upload-[^/]*\.tar$", remote) and len(data) > 512:
        data = data[:512] + bytes([data[512] ^ 0xFF]) + data[513:]
        corrupted = True
    target = fs_path(remote)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    n = bump(state, "scp_upload")
    state.setdefault("uploads", []).append({"remote": remote, "bytes": len(data), "corrupted": corrupted})
    run_hooks(state, "scp_upload", n)
    return out("scp_upload", 0)


def strip_options(argv: list[str]) -> list[str]:
    rest, i = [], 0
    while i < len(argv):
        if argv[i] == "-o":
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    return rest


def main() -> int:
    tool, args = sys.argv[1], strip_options(sys.argv[2:])
    state = load_state()
    seq = state["seq"] = state.get("seq", 0) + 1
    if tool == "ssh":
        command = " ".join(args[1:])
        script = sys.stdin.read() if command == "sh -s" else None
        kind, code, stdout, stderr = handle_ssh(state, command, script)
        entry = {"seq": seq, "tool": "ssh", "kind": kind, "exit": code, "command": command[:1500]}
        if script is not None:
            entry["script_head"] = script[:300]
    elif tool == "scp":
        kind, code, stdout, stderr = handle_scp(state, args[-2], args[-1])
        entry = {"seq": seq, "tool": "scp", "kind": kind, "exit": code, "command": f"{args[-2]} -> {args[-1]}"}
    else:
        kind, code, stdout, stderr, entry = "unknown_tool", 97, "", f"unknown tool {tool}\n", {"seq": seq, "kind": "unknown_tool"}
    log(entry)
    save_state(state)
    sys.stdout.buffer.write(stdout.encode("utf-8"))
    sys.stderr.buffer.write(stderr.encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
