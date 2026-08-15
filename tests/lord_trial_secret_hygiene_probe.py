"""Non-destructive proof that the disposable Lord Trial runtime cannot
create (or read) ``secret_key.txt``.

Why a probe rather than a clean-directory experiment
----------------------------------------------------
``app.py`` pins the key file to its own directory
(``os.path.dirname(os.path.abspath(__file__))``), so "run it somewhere
without a secret_key.txt" would mean copying the whole repository. It is
also the wrong experiment: the interesting claim is not "no file appeared
this time" but "the file is never opened at all", which is strictly
stronger and observable directly.

``sys.addaudithook`` sees every ``open`` **before** it happens, so a hook
that raises prevents the access rather than undoing it: nothing is created,
and nothing is read. That is what both configurations below observe.

Configurations
--------------
``guarded_with_secret``
    The harness's own hygiene (synthetic ``SECRET_KEY`` + armed guard),
    then ``import app``. Expected: import succeeds, zero accesses to
    ``secret_key.txt``, and ``app.secret_key`` is the synthetic value —
    i.e. ``app.py`` took its environment branch and never looked at the
    file.

``guarded_without_secret``
    The same harness guard, but with ``SECRET_KEY`` deliberately removed
    from the environment before ``import app``. This is the control that
    demonstrates the root cause *and* that the guard is independently
    sufficient: ``app.py`` reaches for ``secret_key.txt``, the guard
    refuses, the import fails closed, and the file on disk is provably
    untouched (compared by ``os.stat`` — size/mtime/inode only, never
    contents).

``guarded_without_secret_and_file_absent``
    As above, plus ``os.path.exists`` reports *that one path* as absent, so
    ``app.py``'s third branch — the one that generates and **writes** a new
    key file — is the branch actually taken. This is what created the stray
    file in the first place, reproduced here as a real observation (an
    ``open`` in write mode) rather than an inference from reading the
    source. The guard refuses that write, so no file is created and the
    existing one is still untouched.

``guard_blocks_decoy_write``
    Attempts to create a brand-new ``secret_key.txt`` in a temporary
    directory. The guard must prevent the creation, not clean it up
    afterwards.

``import_real_app_refuses_without_secret``
    The harness's own precondition check, independent of the audit hook:
    ``_import_real_app()`` must refuse rather than let ``app.py`` fall
    through to its key-writing branch.

A further configuration — no ``SECRET_KEY``, no guard — is deliberately
**not** run: that is precisely the combination that writes the file, and
this probe must never mutate the working tree.

Usage:
    python tests/lord_trial_secret_hygiene_probe.py            # both, JSON report
    python tests/lord_trial_secret_hygiene_probe.py --config guarded_with_secret
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = REPO_ROOT / 'secret_key.txt'
CONFIGS = (
    'guarded_with_secret',
    'guarded_without_secret',
    'guarded_without_secret_and_file_absent',
    'guard_blocks_decoy_write',
    'import_real_app_refuses_without_secret',
)

# Importing the harness arms a process-wide audit hook and assigns
# SECRET_KEY. That is correct inside the harness's own process and wrong
# inside a shared pytest session -- tests/deployment legitimately writes a
# decoy secret_key.txt into a temporary repo fixture. Every configuration
# here therefore runs as its own subprocess, and the pytest gate only ever
# reads this probe's report.


def _stat_fingerprint():
    """Identity of the key file without opening it.

    ``os.stat`` reads directory metadata only. Contents are never accessed,
    which is the point: this establishes "unchanged" without ever learning
    what the file says.
    """
    try:
        info = KEY_FILE.stat()
    except FileNotFoundError:
        return {'exists': False}
    return {
        'exists': True,
        'size': info.st_size,
        'mtime_ns': info.st_mtime_ns,
        'inode': info.st_ino,
    }


def _run_config(config):
    """Run one configuration in this process and return its observation."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / 'tests'))

    before = _stat_fingerprint()

    # Importing the harness module is what arms both mechanisms; that is the
    # real guard under test, not a reimplementation of it.
    import lord_trial_natural_runtime as harness

    if config.startswith('guarded_without_secret') or config.endswith('_without_secret'):
        os.environ.pop('SECRET_KEY', None)

    if config == 'guarded_without_secret_and_file_absent':
        # Report only this one path as absent, so app.py takes its
        # key-generating branch. Nothing on disk is touched: the file is
        # never opened, deleted, renamed or moved -- only a single
        # existence answer is substituted.
        real_exists = os.path.exists
        target = str(KEY_FILE)

        def _exists(path):
            try:
                if os.path.abspath(os.fspath(path)) == target:
                    return False
            except TypeError:
                pass
            return real_exists(path)

        os.path.exists = _exists

    observation = {
        'config': config,
        'secret_key_env_present': bool(os.environ.get('SECRET_KEY')),
        'key_file_before': before,
    }

    if config == 'guard_blocks_decoy_write':
        # A brand-new file named secret_key.txt, in a temporary directory,
        # far away from the repository's own. The guard must prevent its
        # creation outright rather than clean it up afterwards.
        import tempfile

        with tempfile.TemporaryDirectory(prefix='lord-trial-secret-decoy-') as scratch:
            decoy = os.path.join(scratch, 'secret_key.txt')
            try:
                with open(decoy, 'w', encoding='utf-8') as handle:
                    handle.write('never reached')
            except BaseException as exc:  # noqa: BLE001
                observation['decoy_error_type'] = type(exc).__name__
                observation['decoy_error_is_guard'] = 'secret_key.txt' in str(exc)
            else:
                observation['decoy_error_type'] = None
                observation['decoy_error_is_guard'] = False
            observation['decoy_created'] = os.path.exists(decoy)
        observation['secret_file_access_attempts'] = list(harness.SECRET_FILE_ACCESS_ATTEMPTS)
        observation['key_file_after'] = _stat_fingerprint()
        observation['key_file_unchanged'] = (
            observation['key_file_before'] == observation['key_file_after']
        )
        return observation

    if config == 'import_real_app_refuses_without_secret':
        # The harness's own precondition, independent of the audit hook:
        # it must refuse to import app rather than let app.py fall through
        # to its key-writing branch.
        try:
            harness._import_real_app()
        except harness.HarnessUnavailable as exc:
            observation['refused'] = True
            observation['refusal_mentions_secret_key'] = 'SECRET_KEY' in str(exc)
        except BaseException as exc:  # noqa: BLE001
            observation['refused'] = False
            observation['unexpected_error_type'] = type(exc).__name__
        else:
            observation['refused'] = False
        observation['secret_file_access_attempts'] = list(harness.SECRET_FILE_ACCESS_ATTEMPTS)
        observation['key_file_after'] = _stat_fingerprint()
        observation['key_file_unchanged'] = (
            observation['key_file_before'] == observation['key_file_after']
        )
        return observation

    try:
        import app as app_module
    except BaseException as exc:  # noqa: BLE001 - the failure itself is the result
        observation['import_ok'] = False
        observation['import_error_type'] = type(exc).__name__
        observation['import_error_is_guard'] = 'secret_key.txt' in str(exc)
    else:
        observation['import_ok'] = True
        observation['app_secret_key_is_synthetic'] = (
            app_module.app.secret_key == harness.SYNTHETIC_TEST_SECRET_KEY
        )
        observation['app_key_file_path_basename'] = os.path.basename(app_module._KEY_FILE)

    observation['secret_file_access_attempts'] = list(harness.SECRET_FILE_ACCESS_ATTEMPTS)
    observation['key_file_after'] = _stat_fingerprint()
    observation['key_file_unchanged'] = (
        observation['key_file_before'] == observation['key_file_after']
    )
    return observation


def _run_config_subprocess(config):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), '--config', config],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
    )
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            with contextlib.suppress(ValueError):
                return json.loads(line)
    raise RuntimeError(
        f'no observation JSON from {config} (exit {result.returncode})\n'
        f'--- stdout ---\n{result.stdout[-2000:]}\n--- stderr ---\n{result.stderr[-2000:]}'
    )


def evaluate(observations):
    """Turn the two observations into the claims this probe exists to make."""
    with_secret = observations['guarded_with_secret']
    without_secret = observations['guarded_without_secret']
    file_absent = observations['guarded_without_secret_and_file_absent']
    decoy = observations['guard_blocks_decoy_write']
    precondition = observations['import_real_app_refuses_without_secret']
    write_attempts = [
        attempt for attempt in file_absent['secret_file_access_attempts']
        if 'w' in str(attempt.get('mode', '')).lower()
    ]
    return {
        # The runtime's normal path never touches the file.
        'HARNESS_CREATES_SECRET_KEY_FILE': (
            'YES' if with_secret['secret_file_access_attempts'] else 'NO'
        ),
        'SYNTHETIC_SECRET_IN_USE': with_secret.get('app_secret_key_is_synthetic') is True,
        'APP_IMPORT_OK_UNDER_HARNESS': with_secret.get('import_ok') is True,
        # Root cause, demonstrated rather than asserted.
        'APP_REACHES_FOR_KEY_FILE_WITHOUT_SECRET_KEY': bool(
            without_secret['secret_file_access_attempts']
        ),
        # ...and the guard alone is sufficient even then.
        'GUARD_BLOCKS_WITHOUT_SECRET_KEY': (
            without_secret.get('import_ok') is False
            and without_secret.get('import_error_is_guard') is True
        ),
        # The creation branch itself, observed rather than inferred.
        'APP_WRITES_KEY_FILE_WHEN_ABSENT_AND_NO_SECRET_KEY': bool(write_attempts),
        'GUARD_BLOCKS_THAT_WRITE': bool(
            write_attempts
            and all(attempt.get('blocked') is True for attempt in write_attempts)
            and file_absent.get('import_ok') is False
        ),
        'GUARD_BLOCKS_A_BRAND_NEW_KEY_FILE': (
            decoy.get('decoy_created') is False
            and decoy.get('decoy_error_is_guard') is True
        ),
        'IMPORT_REAL_APP_REFUSES_WITHOUT_SECRET': (
            precondition.get('refused') is True
            and precondition.get('refusal_mentions_secret_key') is True
        ),
        'KEY_FILE_UNCHANGED_BY_PROBE': all(
            observation['key_file_unchanged'] for observation in observations.values()
        ),
        'KEY_FILE_CONTENT_READ': False,
    }


def main(argv=None):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--config', choices=CONFIGS)
    args = parser.parse_args(argv)

    if args.config:
        print(json.dumps(_run_config(args.config)), flush=True)
        return 0

    observations = {config: _run_config_subprocess(config) for config in CONFIGS}
    verdict = evaluate(observations)
    report = {
        'probe': 'e10_lord_autonext_harness_secret_hygiene',
        'key_file_path_basename': KEY_FILE.name,
        'verdict': verdict,
        'observations': observations,
    }
    print(json.dumps(report, indent=2), flush=True)
    ok = (
        verdict['HARNESS_CREATES_SECRET_KEY_FILE'] == 'NO'
        and verdict['SYNTHETIC_SECRET_IN_USE']
        and verdict['APP_IMPORT_OK_UNDER_HARNESS']
        and verdict['GUARD_BLOCKS_WITHOUT_SECRET_KEY']
        and verdict['GUARD_BLOCKS_THAT_WRITE']
        and verdict['GUARD_BLOCKS_A_BRAND_NEW_KEY_FILE']
        and verdict['IMPORT_REAL_APP_REFUSES_WITHOUT_SECRET']
        and verdict['KEY_FILE_UNCHANGED_BY_PROBE']
    )
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
