"""Foundation gate for the E10 Lord Trial auto-next investigation runtime.

Two tiers:

* Tier 1 (``TestOldHarnessBlindSpot``) — source-level, no docker, always
  runs.  Pins the exact reason the previous acceptance scripts could not see
  this defect, and pins the client-side fields that make it so, straight
  from ``index.html``/``app.py``.  These are the assertions that would start
  failing if someone "fixed" the harness by re-introducing a shortcut.

* Tier 2 (``TestDisposableRuntime``) — runs the disposable real-path runtime
  in ``tests/lord_trial_natural_runtime.py`` as a subprocess and asserts on
  its self-check report.  Skipped (never silently passed) when docker is
  unavailable.

Nothing here answers the auto-next question itself; that is the trace task's
job.  This file only proves the instrument is honest.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / 'tests' / 'lord_trial_natural_runtime.py'
PROBE = REPO_ROOT / 'tests' / 'lord_trial_secret_hygiene_probe.py'
QUESTIONS_FIXTURE = REPO_ROOT / 'tests' / 'fixtures' / 'lord_trial_natural' / 'questions.json'
INDEX = (REPO_ROOT / 'index.html').read_text(encoding='utf-8')
APP = (REPO_ROOT / 'app.py').read_text(encoding='utf-8')

# The #351-era acceptance scripts, and the exact substitution that blinded
# them.  Referenced by path so a rename cannot quietly invalidate this test.
OLD_SHORTCUT_SCRIPTS = (
    'tests/e2e/run_e10_owner_ipad_acceptance_hotfix_002.mjs',
    'tests/e2e/run_e10_lord_trial_visible_board_recovery_contract.mjs',
)

# Fields ``submitSRS()`` reads from the review response *before* it reaches
# the Boss advancement authority.  Under an {"ok":true}-only response every
# one of these branches is dead, so any failure originating in them is
# unobservable.
SUBMITSRS_PRE_AUTHORITY_FIELDS = (
    'monster', 'pet', 'practice', 'player', 'sp', 'loot', 'appearance_loot',
    'new_appearance_items', 'quest_updates', 'combo_streak', 'ranked_up',
    'xp_gain', 'shield_used', 'pet_xp_gained',
)


def _submit_srs_block():
    start = INDEX.index('async function submitSRS(grade){')
    end = INDEX.index('async function loadQuestion(', start)
    return INDEX[start:end]


class TestOldHarnessBlindSpot:
    """Why a new foundation was required at all."""

    def test_old_acceptance_scripts_fulfil_the_review_route_with_ok_true(self):
        for relative in OLD_SHORTCUT_SCRIPTS:
            source = (REPO_ROOT / relative).read_text(encoding='utf-8')
            assert '/api/srs/review' in source, relative
            assert "JSON.stringify({ ok: true })" in source, (
                f'{relative} no longer contains the documented {{"ok":true}} '
                'review shortcut; update this gate deliberately rather than '
                'silently losing the record of the blind spot'
            )

    def test_submit_srs_reads_response_fields_before_boss_authority(self):
        block = _submit_srs_block()
        authority = block.index('await _handleBossAnswer(grade, bossAnswerContext);')
        before_authority = block[:authority]
        for field in SUBMITSRS_PRE_AUTHORITY_FIELDS:
            assert f'data.{field}' in before_authority, field

    def test_boss_authority_is_the_only_boss_advancement_and_next_is_not(self):
        block = _submit_srs_block()
        assert block.count('await _handleBossAnswer(grade, bossAnswerContext);') == 1
        # The generic fallback in the enclosing finally.
        assert 'if (shouldAdvance) {' in block
        assert 'nextQuestion();' in block
        # ...which cannot stand in for the Boss transition.
        next_start = INDEX.index('function nextQuestion({ mapBattleV1Transition = false } = {}){')
        next_block = INDEX[next_start:INDEX.index('function prevQuestion', next_start)]
        boss_guard = next_block[next_block.index('if (_bossMode)'):]
        assert '_syncBossNextButton();' in boss_guard
        assert 'return;' in boss_guard

    def test_real_review_route_returns_far_more_than_ok(self):
        start = APP.index("return jsonify({\n        'ok': True, 'ease_factor': ef,")
        payload = APP[start:start + 1400]
        for field in ('new_badges', 'stats', 'xp_gain', 'combo_mult', 'pet',
                      'practice', 'training', 'new_appearance_items', 'monster_data'):
            assert field in payload, field


class TestDisposableQuestionFixture:
    """The corpus the runtime uses is disposable and never the canonical one."""

    def test_fixture_is_a_self_contained_lord_trial_zone_set(self):
        records = json.loads(QUESTIONS_FIXTURE.read_text(encoding='utf-8'))
        assert len(records) >= 20, 'a Lord Trial exam is BOSS_EXAM_SIZE questions'
        ids = [record['id'] for record in records]
        assert len(set(ids)) == len(ids)
        for record in records:
            assert record['topic'] == '1圍棋新手村', record['id']
            assert record['enabled'] is True
            assert record['content'].startswith('(;GM[1]')
            assert len(record['accepted_moves']) == 1
        # Distinct answers, so a later trace can tell one question from the next.
        answers = {(m['x'], m['y']) for record in records for m in record['accepted_moves']}
        assert len(answers) == len(records)

    def test_harness_never_points_at_the_canonical_corpus(self):
        """QUESTIONS_JSON_PATH must come from a disposable fixture.

        Asserted as an invariant rather than by pinning one source line, so
        adding a corpus (multi_ply) does not require editing this test while
        still catching a regression to the canonical questions.json.
        """
        source = HARNESS.read_text(encoding='utf-8')
        assert "os.environ['QUESTIONS_JSON_PATH'] = str(questions_fixture)" in source
        assert "'single_ply': _FIXTURE_DIR / 'questions.json'" in source
        # Every declared corpus lives under the disposable fixture directory.
        assert "_FIXTURE_DIR = REPO_ROOT / 'tests' / 'fixtures' / 'lord_trial_natural'" in source
        assert "REPO_ROOT / 'questions.json'" not in source

    def test_multi_ply_fixture_carries_a_real_opponent_reply(self):
        """The multi-ply corpus must take onBoardClick's async branch.

        A 1-ply answer resolves synchronously; only an answer whose node has
        a child move drives `answering = true` -> 400ms setTimeout ->
        opponent reply -> submitSRS(3), which is Production's ordering.
        """
        path = REPO_ROOT / 'tests' / 'fixtures' / 'lord_trial_natural' / 'questions_multi_ply.json'
        records = json.loads(path.read_text(encoding='utf-8'))
        assert len(records) >= 20
        for record in records:
            content = record['content']
            # Player move followed by an opponent reply in the same variation.
            assert ';B[' in content and ';W[' in content, record['id']
            assert record['topic'] == '1圍棋新手村'
            # The accepted move must equal the SGF's own first move, or
            # _injectAcceptedAnswerNodes (index.html:10768) would append a
            # childless duplicate node and the click would resolve
            # synchronously after all, silently defeating the fixture.
            move = record['accepted_moves'][0]
            first = content.split(';B[', 1)[1][:2]
            assert first == chr(ord('a') + move['x']) + chr(ord('a') + move['y']), record['id']


class TestHarnessSecretHygiene:
    """The harness must not be able to create (or read) secret_key.txt.

    app.py resolves its session key at import time (app.py:116-126): env
    var, else an existing secret_key.txt, else **generate and write one into
    the working tree**. That third branch is a real side effect of merely
    importing app with no SECRET_KEY set, and the file is untracked and not
    gitignored. None of these tests ever inspect the contents of a
    secret_key.txt that happens to exist.
    """

    def test_synthetic_secret_is_injected_at_module_import(self):
        source = HARNESS.read_text(encoding='utf-8')
        install_at_module_level = source.index('\ninstall_secret_hygiene()\n')
        # Established before the only function that imports app, and before
        # the companion-module resolution that precedes it.
        assert install_at_module_level < source.index('def _import_real_app(')
        assert install_at_module_level < source.index('def resolve_companion_modules(')
        assert 'SYNTHETIC_TEST_SECRET_KEY' in source

    def test_synthetic_secret_is_a_deterministic_literal(self):
        """Deterministic and obviously synthetic, checked without importing.

        Importing the harness arms a process-wide audit hook and assigns
        SECRET_KEY, which must not happen inside a shared pytest session --
        tests/deployment legitimately writes a decoy secret_key.txt into a
        temporary repo fixture. Everything behavioural is therefore checked
        through the probe's subprocesses instead.
        """
        source = HARNESS.read_text(encoding='utf-8')
        line = next(
            line for line in source.splitlines()
            if line.startswith('SYNTHETIC_TEST_SECRET_KEY = ')
        )
        value = line.split(' = ', 1)[1].strip()
        assert value.startswith("'") and value.endswith("'")
        # A literal, not a per-run value: no token/uuid/random generation.
        for generator in ('secrets.', 'uuid.', 'random.', 'os.urandom', 'time.'):
            assert generator not in value
        assert 'synthetic' in value and 'test' in value
        assert 'not-a-production-key' in value

    def test_harness_import_does_not_leak_into_this_pytest_session(self):
        """The gate itself must not arm the guard for unrelated tests."""
        assert 'lord_trial_natural_runtime' not in sys.modules

    def test_probe_proves_the_harness_never_touches_the_key_file(self):
        """End-to-end proof, run as its own processes.

        See tests/lord_trial_secret_hygiene_probe.py for why this is an
        access-observation rather than a clean-directory experiment.
        """
        result = subprocess.run(
            [sys.executable, str(PROBE)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
        )
        matches = re.findall(r'^\{\n.*?^\}$', result.stdout, flags=re.S | re.M)
        assert matches, (
            f'no probe report (exit {result.returncode})\n'
            f'{result.stdout[-2000:]}\n{result.stderr[-2000:]}'
        )
        verdict = json.loads(matches[-1])['verdict']
        assert verdict['HARNESS_CREATES_SECRET_KEY_FILE'] == 'NO'
        assert verdict['SYNTHETIC_SECRET_IN_USE'] is True
        assert verdict['APP_IMPORT_OK_UNDER_HARNESS'] is True
        # Root cause, demonstrated: without SECRET_KEY the real app reaches
        # for the file, and when it is absent that reach is a write.
        assert verdict['APP_REACHES_FOR_KEY_FILE_WITHOUT_SECRET_KEY'] is True
        assert verdict['APP_WRITES_KEY_FILE_WHEN_ABSENT_AND_NO_SECRET_KEY'] is True
        # ...and the guard alone stops it either way.
        assert verdict['GUARD_BLOCKS_WITHOUT_SECRET_KEY'] is True
        assert verdict['GUARD_BLOCKS_THAT_WRITE'] is True
        assert verdict['GUARD_BLOCKS_A_BRAND_NEW_KEY_FILE'] is True
        # The harness's own precondition, independent of the audit hook.
        assert verdict['IMPORT_REAL_APP_REFUSES_WITHOUT_SECRET'] is True
        assert verdict['KEY_FILE_UNCHANGED_BY_PROBE'] is True
        assert verdict['KEY_FILE_CONTENT_READ'] is False

    def test_no_test_only_file_reads_the_key_file(self):
        """Nothing here may open secret_key.txt, in any mode.

        Metadata (os.stat) is fine and is how the probe proves the file was
        left alone; opening it is not.
        """
        for path in (HARNESS, PROBE):
            source = path.read_text(encoding='utf-8')
            for forbidden in ("open(KEY_FILE", "KEY_FILE.read", "read_text()",
                              "open(_KEY_FILE", "secret_key.txt', 'r'"):
                assert forbidden not in source, f'{path.name}: {forbidden}'

    def test_production_secret_loading_is_untouched(self):
        """The fix is environment input only; app.py's own logic is intact."""
        assert "if os.environ.get('SECRET_KEY'):" in APP
        assert "app.secret_key = os.environ['SECRET_KEY']" in APP
        assert "elif os.path.exists(_KEY_FILE):" in APP
        assert "with open(_KEY_FILE, 'w') as f:" in APP


def _docker_available():
    if shutil.which('docker') is None:
        return False
    try:
        result = subprocess.run(
            ['docker', 'version', '--format', '{{.Server.Version}}'],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


@pytest.fixture(scope='module')
def selfcheck_report():
    if not _docker_available():
        pytest.skip('docker server unavailable for the disposable Lord Trial runtime')
    result = subprocess.run(
        [sys.executable, str(HARNESS), 'selfcheck'],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=900,
    )
    if result.returncode == 3:
        pytest.skip(f'disposable runtime unavailable: {result.stdout.strip()[-500:]}')
    # The runtime shares stdout with werkzeug/startup logging; the report is
    # the last complete JSON object on the stream.
    matches = re.findall(r'^\{\n.*?^\}$', result.stdout, flags=re.S | re.M)
    assert matches, (
        f'no JSON report on stdout (exit {result.returncode})\n'
        f'--- stdout ---\n{result.stdout[-3000:]}\n--- stderr ---\n{result.stderr[-3000:]}'
    )
    return json.loads(matches[-1])


class TestDisposableRuntime:
    """Phase 4/6: the new foundation is not another synthetic shortcut."""

    def test_authenticated_disposable_session_is_real(self, selfcheck_report):
        checks = selfcheck_report['checks']
        assert checks['AUTH_SESSION_REAL'] is True
        # A real credential check, not a session handed out to anyone.
        assert checks['AUTH_REJECTS_BAD_CREDENTIAL'] is True
        assert 'session' in selfcheck_report['evidence']['session_cookie_names']

    def test_database_is_disposable_and_local(self, selfcheck_report):
        assert selfcheck_report['checks']['DISPOSABLE_DB_REAL'] is True
        host = selfcheck_report['evidence']['database_url_host']
        assert host.startswith('127.0.0.1:')
        assert 'godokoro' not in host and '152.69.200.105' not in host

    def test_real_index_and_srs_js_are_served(self, selfcheck_report):
        checks = selfcheck_report['checks']
        assert checks['REAL_FLASK_APP'] is True
        assert checks['REAL_INDEX_SUBMITSRS_PRESENT'] is True
        assert checks['REAL_SRS_JS_LOADED'] is True
        # The authenticated index, not the landing page.
        assert selfcheck_report['evidence']['index_bytes'] > 500000

    def test_boss_attempt_is_real_and_server_signed(self, selfcheck_report):
        checks = selfcheck_report['checks']
        assert checks['BOSS_ATTEMPT_REAL'] is True
        assert checks['BOSS_ATTEMPT_SIGNED'] is True
        # A client-chosen attempt marker is refused by the real route, so the
        # accepted one demonstrably came from the signed server session.
        assert checks['BOSS_ATTEMPT_CONTEXT_ENFORCED'] is True
        assert selfcheck_report['evidence']['forged_boss_context_error'] == (
            'invalid_boss_attempt_context'
        )

    def test_review_route_is_real_and_production_shaped(self, selfcheck_report):
        checks = selfcheck_report['checks']
        assert checks['REAL_REVIEW_ROUTE_REACHABLE'] is True
        assert checks['REVIEW_RESPONSE_IS_ONLY_OK_TRUE'] is False
        keys = selfcheck_report['evidence']['REVIEW_RESPONSE_KEYS']
        assert keys != ['ok']
        assert len(keys) > 20
        types = selfcheck_report['evidence']['REVIEW_RESPONSE_TYPES']
        assert types['ok'] == 'bool'
        assert types['stats'] == 'dict'

    def test_every_pre_authority_presentation_gate_can_execute(self, selfcheck_report):
        """Phase 6: field-gated client behaviour is now reachable.

        This asserts capability only.  Which field (if any) is implicated in
        the auto-next failure is deliberately not claimed here.
        """
        absent = selfcheck_report['evidence']['submitsrs_gated_fields_absent']
        assert absent == [], f'still unreachable under this runtime: {absent}'
        present = set(selfcheck_report['evidence']['submitsrs_gated_fields_present'])
        for field in SUBMITSRS_PRE_AUTHORITY_FIELDS:
            assert field in present, field

    def test_review_is_a_durable_server_commit(self, selfcheck_report):
        assert selfcheck_report['checks']['REVIEW_COMMITS_SERVER_SIDE'] is True
        resumed = selfcheck_report['evidence']['boss_resume_body']
        assert resumed['resumed'] is True
        assert resumed['answered_count'] == 1

    def test_runtime_ran_on_the_synthetic_secret_and_never_touched_the_file(
        self, selfcheck_report
    ):
        checks = selfcheck_report['checks']
        assert checks['SYNTHETIC_SECRET_IN_USE'] is True
        assert checks['NO_SECRET_KEY_FILE_ACCESS'] is True
        assert selfcheck_report['evidence']['secret_file_access_attempts'] == []
        # The real session cookie in this same run was signed by that key,
        # so this is not a claim about an unused code path.
        assert checks['AUTH_SESSION_REAL'] is True

    def test_no_companion_module_was_stubbed(self, selfcheck_report):
        """Existing tests stub seven companion modules; this runtime does not.

        If a future environment genuinely cannot import one, that is reported
        here rather than being silently tolerated.
        """
        assert selfcheck_report['runtime']['stubbed_companion_modules'] == {}

    def test_overall_foundation_validation_passes(self, selfcheck_report):
        assert selfcheck_report['ok'] is True
