"""Untrusted pytest diagnostics (loaded with -p g009_release_identity_plugin).

Candidate code shares this interpreter and can forge these diagnostics. This
record alone never proves execution identity or authorizes a release.

It writes nothing unless G009_RELEASE_IDENTITY_RECORD is set; then, at session end, it writes a JSON record with
the nonce from G009_RELEASE_IDENTITY_NONCE (generated fresh by the caller, so a stale record cannot be replayed).
It never changes test collection, outcomes or reports.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

WATCHED_MODULES = ("app", "test_p0_zone4_cinematic_content_route_corrective")
_collection = []
_reports = []


def _sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def pytest_collection_finish(session):
    _collection.clear()
    _reports.clear()
    for item in session.items:
        code = getattr(getattr(item, "obj", None), "__code__", None)
        _collection.append({"nodeid": item.nodeid, "path": str(Path(str(item.path)).resolve()),
                            "code_file": str(Path(code.co_filename).resolve()) if code else None})


def pytest_runtest_logreport(report):
    _reports.append({"nodeid": report.nodeid, "when": report.when, "outcome": report.outcome})


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("G009_RELEASE_IDENTITY_RECORD")
    if not target:
        return
    modules = {}
    for name, module in list(sys.modules.items()):
        short = name.rsplit(".", 1)[-1]
        if short in WATCHED_MODULES or name in WATCHED_MODULES:
            file = getattr(module, "__file__", None)
            modules[name] = {"file": str(Path(file).resolve()) if file else None, "sha256": _sha(file) if file else None}
    record = {
        "schema": "g009-release-identity-record-v1",
        "nonce": os.environ.get("G009_RELEASE_IDENTITY_NONCE"),
        "rootdir": str(Path(str(session.config.rootpath)).resolve()),
        "cwd": str(Path.cwd().resolve()),
        "exitstatus": int(exitstatus),
        "python": {"executable": sys.executable, "version": sys.version.split()[0],
                   "dont_write_bytecode": bool(sys.flags.dont_write_bytecode or sys.dont_write_bytecode),
                   "pycache_prefix": getattr(sys, "pycache_prefix", None)},
        "modules": modules,
        "evidence_trust": "CANDIDATE_CONTROLLED_DIAGNOSTIC_ONLY",
        "collection": list(_collection),
        "reports": list(_reports),
        "junit_sha256": _sha(session.config.option.xmlpath) if getattr(session.config.option, "xmlpath", None) else None,
    }
    Path(target).write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
