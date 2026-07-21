import pathlib
import subprocess
import textwrap
import os
import json

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/release/CommunityRewardsExecutionControl.psm1"
DEPLOY = ROOT / "scripts/release/deploy-release-image.ps1"
ROLLBACK = ROOT / "scripts/release/rollback-release.ps1"
RESUME = ROOT / "scripts/release/resume-community-leaderboard-rewards.ps1"
GRANT = ROOT / "scripts/release/grant-community-leaderboard-rewards-w29.ps1"
RUNBOOK = ROOT / "docs/deployment/community_rewards_controlled_w29_recovery.md"


def source(path):
    return path.read_text(encoding="utf-8")


def render(operation):
    function = {
        "freeze": "New-CommunityRewardsFreezeRemoteScript",
        "resume": "New-CommunityRewardsResumeRemoteScript",
    }[operation]
    command = (
        f"Import-Module '{ROOT / 'scripts/release/ReleaseTooling.psm1'}' -Force -DisableNameChecking; "
        f"Import-Module '{MODULE}' -Force -DisableNameChecking; "
        f"{function} -SchedulerContainer scheduler -ExpectedSchedulerImageId sha256:old "
        "-AppContainer app "
        "-PostgresContainer postgres -ExpectedAppImageId sha256:old -ExpectedAppImageTag app:old "
        "-ExpectedSchedulerImageTag app:old -ComposeDirectory /release -ComposeProject project "
        "-ComposeFile /release/docker-compose.release.yml -EnvFile /protected/.env "
        "-SchedulerService scheduler -AppService app -ComposeEnvironmentPrefix \"GO_ODYSSEY_IMAGE='app:old' QUESTIONS_CONTENT_VOLUME_NAME='go-data'\""
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def pre_stop_probe_source():
    script = render("freeze")
    opening = "<<'__COMMUNITY_ZERO_STATE__'\n"
    closing = "\n__COMMUNITY_ZERO_STATE__"
    start = script.index(opening) + len(opening)
    end = script.index(closing, start)
    return script[start:end].strip()


def post_deploy_probe_source():
    command = (
        f"Import-Module '{ROOT / 'scripts/release/ReleaseTooling.psm1'}' -Force -DisableNameChecking; "
        f"Import-Module '{MODULE}' -Force -DisableNameChecking; "
        "New-CommunityRewardsZeroStateProbeRemoteScript -SchedulerContainer scheduler"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    opening = "<<'__COMMUNITY_ZERO_STATE__'\n"
    closing = "\n__COMMUNITY_ZERO_STATE__"
    start = result.stdout.index(opening) + len(opening)
    end = result.stdout.index(closing, start)
    return result.stdout[start:end].strip()


def resume_probe_source():
    script = render("resume")
    opening = "<<'__COMMUNITY_SETTLED_STATE__'\n"
    closing = "\n__COMMUNITY_SETTLED_STATE__"
    start = script.index(opening) + len(opening)
    end = script.index(closing, start)
    return script[start:end].strip()


def render_exact_w29_grant(operation_directory="/operations/w29", snapshot_file_sha="snapshot-file", preview_file_sha="preview-file", manifest_file_sha="manifest-file"):
    command = (
        f"Import-Module '{ROOT / 'scripts/release/ReleaseTooling.psm1'}' -Force -DisableNameChecking; "
        f"Import-Module '{MODULE}' -Force -DisableNameChecking; "
        "New-CommunityRewardsExactW29GrantRemoteScript "
        "-SchedulerContainer scheduler -ExpectedSchedulerImageTag app:c866f611 "
        "-ExpectedSchedulerImageId sha256:image -ExpectedRevision c866f611 "
        f"-OperationDirectory '{operation_directory}' -OperationId w29-c866f611-20260720T055453Z-c001bcd0 "
        f"-SnapshotFileSha256 {snapshot_file_sha} -PreviewFileSha256 {preview_file_sha} "
        f"-ManifestFileSha256 {manifest_file_sha} -CanonicalSnapshotSha256 canonical-snapshot "
        "-CanonicalPreviewSha256 canonical-preview -WrapperSourceRevision "
        "b019315e5afec532a2e352737bc678b32c62775e"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def render_operator_evidence(operation_directory, stage="invocation_started", status="started", launch_count=0):
    command = (
        f"Import-Module '{ROOT / 'scripts/release/ReleaseTooling.psm1'}' -Force -DisableNameChecking; "
        f"Import-Module '{MODULE}' -Force -DisableNameChecking; "
        "New-CommunityRewardsGrantEvidenceRemoteScript "
        f"-OperationDirectory '{operation_directory}' "
        "-OperationId w29-c866f611-20260720T055453Z-c001bcd0 "
        f"-Stage {stage} -Status {status} -LaunchCount {launch_count} "
        "-WrapperSourceRevision b019315e5afec532a2e352737bc678b32c62775e"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def run_generated_probe(probe_source, mode, *, probe_kind="zero", nonzero_period="", lock="0", malformed="0", failure_field=""):
    prelude = textwrap.dedent(
        r'''
        import builtins, os, sys, types
        mode = os.environ['FAKE_DRIVER_MODE']
        probe_kind = os.environ['FAKE_PROBE_KIND']
        real_import = builtins.__import__

        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, args=()):
                if mode.startswith('sql_failure'): raise RuntimeError('sanitized sql failure')
                self.sql, self.args = sql, args
            def fetchone(self):
                if os.environ['FAKE_MALFORMED'] == '1': return ()
                if 'pg_locks' in self.sql: return (int(os.environ['FAKE_LOCK']),)
                if probe_kind == 'resume':
                    field = os.environ['FAKE_FAILURE_FIELD']
                    if "status <> 'granted'" in self.sql: return (int(field == 'unsettled'),)
                    if "status = 'pending'" in self.sql: return (int(field == 'pending'),)
                    if "status = 'failed'" in self.sql: return (int(field == 'failed'),)
                    if 'GROUP BY user_id' in self.sql: return (int(field == 'duplicate_claims'),)
                    if 'GROUP BY l.claim_id' in self.sql: return (int(field == 'duplicate_components'),)
                    if '2026-W30' in self.args: return (int(field == 'w30'),)
                    if '2026-W29' in self.args: return (21,)
                if os.environ['FAKE_NONZERO_PERIOD'] and os.environ['FAKE_NONZERO_PERIOD'] in self.args:
                    return (1,)
                return (0,)

        class Connection:
            def cursor(self): return Cursor()
            def close(self): pass

        def module(name):
            value = types.ModuleType(name)
            def connect(dsn):
                print('DRIVER=' + name, file=sys.stderr)
                if mode.startswith('connection_failure'): raise RuntimeError('sanitized connection failure')
                return Connection()
            value.connect = connect
            return value

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'psycopg':
                if mode in ('v3', 'connection_failure', 'sql_failure'): return module('psycopg')
                if mode == 'unexpected_import_failure': raise RuntimeError('unexpected import failure')
                if mode == 'nested_missing': raise ModuleNotFoundError("No module named 'dependency'", name='dependency')
                raise ModuleNotFoundError("No module named 'psycopg'", name='psycopg')
            if name == 'psycopg2':
                if mode in ('v2', 'connection_failure_v2', 'sql_failure_v2'):
                    return module('psycopg2')
                raise ModuleNotFoundError("No module named 'psycopg2'", name='psycopg2')
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = fake_import
        '''
    )
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": "postgresql://protected-user:protected-password@db/private",
        "FAKE_DRIVER_MODE": mode,
        "FAKE_NONZERO_PERIOD": nonzero_period,
        "FAKE_LOCK": lock,
        "FAKE_MALFORMED": malformed,
        "FAKE_PROBE_KIND": probe_kind,
        "FAKE_FAILURE_FIELD": failure_field,
    })
    return subprocess.run(
        ["python", "-c", prelude + "\n" + probe_source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def run_pre_stop_probe(mode, **kwargs):
    return run_generated_probe(pre_stop_probe_source(), mode, **kwargs)


def test_changed_powershell_files_parse():
    paths = (MODULE, DEPLOY, ROLLBACK, RESUME, GRANT)
    command = ";".join(
        f"$t=$null;$e=$null;[Management.Automation.Language.Parser]::ParseFile('{p}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{exit 9}}"
        for p in paths
    )
    assert subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        timeout=30,
        check=False,
    ).returncode == 0


def test_pre_stop_probe_prefers_psycopg_v3_and_normalizes_zero_state():
    result = run_pre_stop_probe("v3")
    assert result.returncode == 0, result.stderr
    assert "DRIVER=psycopg" in result.stderr
    assert "DRIVER=psycopg2" not in result.stderr
    assert '"w29_lock": 0' in result.stdout


def test_pre_stop_probe_falls_back_to_psycopg2_only_when_v3_is_missing():
    v3 = run_pre_stop_probe("v3")
    v2 = run_pre_stop_probe("v2")
    assert v2.returncode == 0, v2.stderr
    assert "DRIVER=psycopg2" in v2.stderr
    assert v2.stdout == v3.stdout


@pytest.mark.parametrize("mode", ["none", "unexpected_import_failure", "nested_missing"])
def test_pre_stop_probe_driver_import_failures_are_fail_closed(mode):
    result = run_pre_stop_probe(mode)
    assert result.returncode != 0
    assert "DRIVER=" not in result.stderr
    assert "docker stop" not in pre_stop_probe_source()


@pytest.mark.parametrize(
    "mode", ["connection_failure", "connection_failure_v2", "sql_failure", "sql_failure_v2"]
)
def test_pre_stop_probe_connection_and_query_failures_are_fail_closed_and_redacted(mode):
    result = run_pre_stop_probe(mode)
    assert result.returncode != 0
    assert "protected-password" not in result.stderr
    assert "protected-user" not in result.stderr
    assert "postgresql://" not in result.stderr
    assert "docker stop" not in pre_stop_probe_source()


@pytest.mark.parametrize(
    ("mode", "period", "lock"),
    [("v3", "2026-W29", "0"), ("v2", "2026-W30", "0"), ("v3", "", "1"), ("v2", "", "1")],
)
def test_pre_stop_probe_nonzero_state_and_lock_are_fail_closed(mode, period, lock):
    result = run_pre_stop_probe(mode, nonzero_period=period, lock=lock)
    assert result.returncode == 33


@pytest.mark.parametrize("mode", ["v3", "v2"])
def test_pre_stop_probe_malformed_results_are_fail_closed(mode):
    result = run_pre_stop_probe(mode, malformed="1")
    assert result.returncode != 0


def test_all_three_probe_paths_share_one_driver_compatibility_contract():
    module = source(MODULE)
    assert module.count("except ModuleNotFoundError as exc:") == 1
    for probe in (pre_stop_probe_source(), post_deploy_probe_source(), resume_probe_source()):
        assert "import psycopg" in probe
        assert "import psycopg2 as psycopg" in probe
        assert "if exc.name != 'psycopg':" in probe


@pytest.mark.parametrize("probe_source", [post_deploy_probe_source, resume_probe_source])
def test_remaining_probes_produce_identical_results_for_v3_and_v2(probe_source):
    kind = "resume" if probe_source is resume_probe_source else "zero"
    v3 = run_generated_probe(probe_source(), "v3", probe_kind=kind)
    v2 = run_generated_probe(probe_source(), "v2", probe_kind=kind)
    assert v3.returncode == 0, v3.stderr
    assert v2.returncode == 0, v2.stderr
    assert v3.stdout == v2.stdout
    assert "DRIVER=psycopg" in v3.stderr
    assert "DRIVER=psycopg2" in v2.stderr


@pytest.mark.parametrize("probe_source", [post_deploy_probe_source, resume_probe_source])
@pytest.mark.parametrize("mode", ["none", "unexpected_import_failure", "nested_missing"])
def test_remaining_probes_import_failures_are_fail_closed(probe_source, mode):
    kind = "resume" if probe_source is resume_probe_source else "zero"
    result = run_generated_probe(probe_source(), mode, probe_kind=kind)
    assert result.returncode != 0
    assert "DRIVER=" not in result.stderr


@pytest.mark.parametrize("probe_source", [post_deploy_probe_source, resume_probe_source])
@pytest.mark.parametrize("mode", ["connection_failure", "connection_failure_v2", "sql_failure", "sql_failure_v2"])
def test_remaining_probes_connection_query_failures_are_redacted(probe_source, mode):
    kind = "resume" if probe_source is resume_probe_source else "zero"
    result = run_generated_probe(probe_source(), mode, probe_kind=kind)
    assert result.returncode != 0
    assert "protected-password" not in result.stderr
    assert "protected-user" not in result.stderr
    assert "postgresql://" not in result.stderr


@pytest.mark.parametrize("probe_source", [post_deploy_probe_source, resume_probe_source])
@pytest.mark.parametrize("mode", ["v3", "v2"])
def test_remaining_probes_malformed_results_are_fail_closed(probe_source, mode):
    kind = "resume" if probe_source is resume_probe_source else "zero"
    result = run_generated_probe(probe_source(), mode, probe_kind=kind, malformed="1")
    assert result.returncode != 0


@pytest.mark.parametrize("mode", ["v3", "v2"])
def test_post_deploy_probe_rejects_w29_w30_and_lock(mode):
    for period, lock in (("2026-W29", "0"), ("2026-W30", "0"), ("", "1")):
        result = run_generated_probe(
            post_deploy_probe_source(), mode, nonzero_period=period, lock=lock
        )
        assert result.returncode == 33


@pytest.mark.parametrize("mode", ["v3", "v2"])
@pytest.mark.parametrize(
    "failure_field",
    ["unsettled", "pending", "failed", "duplicate_claims", "duplicate_components", "w30"],
)
def test_resume_probe_rejects_unsettled_duplicate_and_w30_state(mode, failure_field):
    result = run_generated_probe(
        resume_probe_source(), mode, probe_kind="resume", failure_field=failure_field
    )
    assert result.returncode == 41


@pytest.mark.parametrize("mode", ["v3", "v2"])
def test_resume_probe_rejects_active_w29_lock(mode):
    result = run_generated_probe(
        resume_probe_source(), mode, probe_kind="resume", lock="1"
    )
    assert result.returncode == 41


def test_resume_recreates_both_workers_only_after_settled_probe_and_verifies_true():
    script = render("resume")
    settled = script.index("__COMMUNITY_SETTLED_STATE__")
    settled_end = script.index("__COMMUNITY_SETTLED_STATE__", settled + 1)
    recreate = script.index('--force-recreate "$APP_SERVICE" "$SCHEDULER_SERVICE"')
    app_true = script.index('docker exec "$APP" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = true')
    scheduler_true = script.index('docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = true')
    assert settled < settled_end < recreate < app_true < scheduler_true
    assert "w29_duplicate_claims" in script
    assert "w29_duplicate_components" in script
    assert "w29_lock" in script


def test_freeze_remote_contract_has_zero_race_order_and_old_image_preservation():
    script = render("freeze")
    ordered = (
        "test \"$(docker inspect \"$SCHEDULER\" --format '{{.Image}}')\" = \"$EXPECTED_IMAGE_ID\"",
        "values != [b\"true\"]",
        'APP_COMMUNITY="$(docker exec "$APP" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)"',
        'SCHEDULER_COMMUNITY="$(docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)"',
        "true:true) COMMUNITY_FREEZE_START_STATE=active",
        "false:false) COMMUNITY_FREEZE_START_STATE=already_frozen",
        "result['w29_lock']",
        "docker stop \"$SCHEDULER\"",
        "docker stop \"$APP\"",
        "--format '{{.State.Status}}')\" = exited",
        "docker exec -i \"$POSTGRES\"",
        "test \"$POST_STOP_TOTAL\" = 0",
        "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false docker compose",
        "--force-recreate \"$APP_SERVICE\" \"$SCHEDULER_SERVICE\"",
        "test \"$(docker inspect \"$SCHEDULER\" --format '{{.Image}}')\" = \"$EXPECTED_IMAGE_ID\"",
        "printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)\" = false",
    )
    positions = []
    cursor = 0
    for item in ordered:
        cursor = script.index(item, cursor)
        positions.append(cursor)
        cursor += len(item)
    assert positions == sorted(positions)
    assert "2026-W29" in script and "2026-W30" in script
    assert script.count("SELECT count(*) FROM leaderboard_reward_claims") == 2
    assert 'force-recreate "$APP_SERVICE" "$SCHEDULER_SERVICE"' in script
    assert 'docker exec "$APP" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = false' in script
    assert all(table in script for table in (
        "leaderboard_reward_claims", "leaderboard_snapshots", "leaderboard_reward_component_log", "pg_locks"
    ))
    assert "latest" not in script.lower()


def test_freeze_accepts_only_exact_active_or_already_frozen_runtime_matrix():
    script = render("freeze")
    assert 'case "$APP_COMMUNITY" in true|false) ;; *) exit 34 ;; esac' in script
    assert 'case "$SCHEDULER_COMMUNITY" in true|false) ;; *) exit 35 ;; esac' in script
    assert "true:true) COMMUNITY_FREEZE_START_STATE=active" in script
    assert "false:false) COMMUNITY_FREEZE_START_STATE=already_frozen" in script
    assert "*) exit 36 ;;" in script
    assert "start_state" in script
    assert "values != [b\"true\"]" in script


def test_already_frozen_contract_keeps_explicit_false_and_never_reenables_community():
    script = render("freeze")
    already_frozen = script.index("false:false) COMMUNITY_FREEZE_START_STATE=already_frozen")
    recreate = script.index('--force-recreate "$APP_SERVICE" "$SCHEDULER_SERVICE"')
    app_false = script.index('docker exec "$APP" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = false')
    scheduler_false = script.index('docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = false')
    assert already_frozen < recreate < app_false < scheduler_false
    assert "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false docker compose" in script
    assert "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true docker compose" not in script
    assert "grant-exact-period-commit" not in script
    assert "community_leaderboard_rewards_manual.py" not in script


def run_freeze_start_state_branch(tmp_path, app_value, scheduler_value):
    git_sh = pathlib.Path(r"C:\Program Files\Git\bin\sh.exe")
    if not git_sh.exists():
        pytest.skip("Git sh is unavailable")
    script = render("freeze")
    start = script.index('APP_COMMUNITY="$(docker exec "$APP" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)"')
    end = script.index('docker exec -i "$SCHEDULER" python', start)
    branch = script[start:end]
    env = os.environ.copy()
    env.update({
        "APP_EFFECTIVE": app_value,
        "SCHEDULER_EFFECTIVE": scheduler_value,
    })
    fake_docker = textwrap.dedent(r'''\
        docker() {
          if [ "$1" = exec ] && [ "$3" = printenv ] && [ "$4" = COMMUNITY_LEADERBOARD_REWARDS_ENABLED ]; then
            case "$2" in
              app) printf '%s\n' "$APP_EFFECTIVE" ;;
              scheduler) printf '%s\n' "$SCHEDULER_EFFECTIVE" ;;
              *) return 90 ;;
            esac
            return 0
          fi
          return 91
        }
    ''')
    return subprocess.run(
        [str(git_sh), "-c", f'{fake_docker}\nAPP=app; SCHEDULER=scheduler; {branch}'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, check=False,
    )


def run_freeze_configured_value_check(tmp_path, content=None):
    script = render("freeze")
    opening = "<<'__COMMUNITY_CONFIGURED_VALUE__'\n"
    closing = "\n__COMMUNITY_CONFIGURED_VALUE__"
    start = script.index(opening) + len(opening)
    end = script.index(closing, start)
    env_file = tmp_path / "protected.env"
    if content is not None:
        env_file.write_text(content, encoding="utf-8")
    return subprocess.run(
        ["python", "-c", script[start:end], str(env_file)],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )


@pytest.mark.parametrize("app_value,scheduler_value", [("true", "true"), ("false", "false")])
def test_freeze_start_state_accepts_only_coherent_active_or_already_frozen_pairs(tmp_path, app_value, scheduler_value):
    result = run_freeze_start_state_branch(tmp_path, app_value, scheduler_value)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("app_value,scheduler_value,exit_code", [
    ("true", "false", 36), ("false", "true", 36),
    ("invalid", "false", 34), ("false", "invalid", 35),
])
def test_freeze_start_state_rejects_inconsistent_or_malformed_runtime_pairs(tmp_path, app_value, scheduler_value, exit_code):
    result = run_freeze_start_state_branch(tmp_path, app_value, scheduler_value)
    assert result.returncode == exit_code


@pytest.mark.parametrize("content,exit_code", [
    ("COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true\n", 0),
    ("COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false\n", 32),
    ("COMMUNITY_LEADERBOARD_REWARDS_ENABLED=yes\n", 32),
    ("", 32),
    (None, 31),
])
def test_freeze_requires_exact_configured_true_value(tmp_path, content, exit_code):
    result = run_freeze_configured_value_check(tmp_path, content)
    assert result.returncode == exit_code


def test_deploy_carries_freeze_through_fixed_image_and_verifies_before_switch():
    text = source(DEPLOY)
    freeze = text.index("New-CommunityRewardsFreezeRemoteScript")
    freeze_verify = text.index("freeze did not preserve the authorized old scheduler image")
    image_load = text.index('Invoke-RemoteText "docker load -i')
    app_switch = text.index("up -d --no-build --no-deps --force-recreate $appComposeService")
    scheduler_switch = text.index("up -d --no-build --no-deps --force-recreate $schedulerComposeService")
    post_zero_state = text.index("New-CommunityRewardsZeroStateProbeRemoteScript")
    assert freeze < freeze_verify < image_load < app_switch < scheduler_switch < post_zero_state
    assert "-CommunityRewardsFrozen:$FreezeCommunityLeaderboardRewards" in text
    assert "GO_DEPLOY_CONTROLLED_W29" in text
    assert "ExpectedCurrentAppImageId" in text and "ExpectedCurrentSchedulerImageId" in text
    assert "requires app and scheduler to share one exact current image" in text


def test_default_deploy_path_remains_conditional_and_requires_normal_gate():
    text = source(DEPLOY)
    assert "if ($FreezeCommunityLeaderboardRewards)" in text
    assert "else { 'GO_DEPLOY' }" in text
    assert "else { 'unchanged' }" in text
    assert "[switch]$FreezeCommunityLeaderboardRewards" in text


def test_controlled_dry_run_describes_every_worker_freeze():
    text = source(DEPLOY)
    assert "stop every old Community worker" in text
    assert "recreate the old app and scheduler on their shared exact image" in text


def test_fail_closed_and_secret_redaction_contracts():
    deploy = source(DEPLOY)
    freeze = render("freeze")
    assert "sanitized remote output withheld" in deploy
    assert "requires exact current app and scheduler image IDs" in deploy
    assert "zero_state_verified" in freeze
    assert "w29_lock" in freeze
    assert "printenv DATABASE_URL" not in deploy
    assert "printenv DATABASE_URL" not in freeze
    assert "cat $ENV_FILE" not in freeze
    assert "set -x" not in freeze


def test_rollback_explicitly_preserves_freeze():
    deploy = source(DEPLOY)
    rollback = source(ROLLBACK)
    assert "$rollbackArguments += '-FreezeCommunityLeaderboardRewards'" in deploy
    assert "[switch]$FreezeCommunityLeaderboardRewards" in rollback
    assert "COMMUNITY_LEADERBOARD_REWARDS_ENABLED='false'" in rollback


def test_resume_is_separate_gated_exact_image_operation_without_reward_calls():
    wrapper = source(RESUME)
    script = render("resume")
    assert "GO_GRANT_W29" in wrapper
    assert "ExpectedSchedulerImageTag" in wrapper and "ExpectedSchedulerImageId" in wrapper
    assert "Enter-RemoteReleaseOperationLock" in wrapper and "Exit-RemoteReleaseOperationLock" in wrapper
    assert "status <> 'granted'" in script
    assert "2026-W30" in script
    assert "w30_snapshots" in script and "w30_components" in script
    assert "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false" not in script
    assert "printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)\" = true" in script
    forbidden = ("grant_exact_period", "grant_coins", "grant_badge", "grant_title", "finalize_leaderboard")
    combined = wrapper.lower() + script.lower()
    assert all(item not in combined for item in forbidden)


def test_runbook_separates_configured_override_effective_and_owner_gates():
    text = source(RUNBOOK)
    for phrase in (
        "configured canonical value",
        "temporary deployment override",
        "effective running value",
        "GO_DEPLOY_CONTROLLED_W29",
        "GO_GRANT_W29",
        "rollback",
        "remains frozen",
    ):
        assert phrase in text


def test_exact_w29_grant_captures_child_stdout_in_remote_host_shell():
    script = render_exact_w29_grant()
    assert '>"$CHILD_STDOUT_FILE" 2>"$CHILD_STDERR_FILE" &' in script
    assert 'wait "$CHILD_PID"' in script
    assert 'test -s "$CHILD_STDOUT_FILE"' in script
    assert ' >"$CONTAINER_OPERATION_DIRECTORY/' not in script
    assert "docker cp" not in script
    assert "recipient-level command output" in script


def test_exact_w29_capture_contract_launches_real_synthetic_child(tmp_path):
    child = tmp_path / "synthetic_grant_child.py"
    result_file = tmp_path / "grant-result.json"
    child.write_text(
        "import json, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
        "'result':'committed','period_key':'2026-W29','claims':21}), encoding='utf-8')\n"
        "print('recipient-sentinel-must-not-be-reported')\n",
        encoding="utf-8",
    )
    child_result = subprocess.run(
        [os.sys.executable, str(child), str(result_file)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False,
    )
    assert child_result.returncode == 0
    assert "recipient-sentinel" in child_result.stdout
    persisted = __import__("json").loads(result_file.read_text(encoding="utf-8"))
    sanitized = {"result": persisted["result"], "period_key": persisted["period_key"], "claims": 21}
    assert sanitized == {"result": "committed", "period_key": "2026-W29", "claims": 21}
    assert "recipient-sentinel" not in __import__("json").dumps(sanitized)
    assert 'LAUNCH_COUNT=1' in render_exact_w29_grant()


def test_exact_w29_grant_validates_before_child_launch_and_persists_atomically():
    script = render_exact_w29_grant()
    launch = script.index('docker exec "$SCHEDULER" python tools/community_leaderboard_rewards_manual.py')
    for gate in (
        "COMMUNITY_LEADERBOARD_REWARDS_ENABLED",
        "EXPECTED_IMAGE_TAG",
        "EXPECTED_IMAGE_ID",
        "EXPECTED_REVISION",
        "SNAPSHOT_FILE_SHA256",
        "PREVIEW_FILE_SHA256",
        "MANIFEST_FILE_SHA256",
        "sudo -n test ! -e \"$RESULT_FILE\"",
    ):
        assert script.index(gate) < launch
    result_check = script.index("__COMMUNITY_W29_RESULT__")
    atomic_move = script.index('sudo -n mv "$RESULT_TEMP_FILE" "$RESULT_FILE"')
    assert launch < result_check < atomic_move
    assert "result_persisted=true" in script[atomic_move:]


def test_exact_w29_grant_has_append_safe_sanitized_stage_evidence():
    script = render_exact_w29_grant()
    stages = (
        "remote_preflight_started", "remote_preflight_passed", "child_command_prepared",
        "child_launch_started", "child_process_created", "child_exit_received",
        "result_read_started", "result_parsed", "result_validated", "result_persisted",
        "cleanup_started", "cleanup_completed",
    )
    for stage in stages:
        assert stage in script
    assert "os.O_APPEND" in script and "os.fsync(fd)" in script
    assert "recipient" not in script[script.index("allowed_stages"):script.index("__COMMUNITY_W29_EVIDENCE__", script.index("allowed_stages"))]
    assert "LAUNCH_COUNT=0" in script
    assert script.count("LAUNCH_COUNT=1") == 1
    assert script.count('docker exec "$SCHEDULER" python tools/community_leaderboard_rewards_manual.py') == 1


def test_exact_w29_wrapper_records_operator_and_remote_exit_stages():
    wrapper = source(GRANT)
    for stage in (
        "invocation_started", "local_validation_passed", "release_lock_acquired",
        "release_lock_released",
    ):
        assert stage in wrapper
    assert "WrapperSourceRevision $wrapperSourceRevision" in wrapper
    assert "$grantRemoteExitCode = [int]$result.exit_code" in wrapper
    assert "grant-execution-evidence.jsonl" in source(MODULE)
    assert "stage == 'release_lock_released'" in source(MODULE)
    assert "current_invocation" in source(MODULE)


def test_operator_stage_evidence_executes_append_only_and_contains_only_allowed_fields(tmp_path):
    git_sh = pathlib.Path(r"C:\Program Files\Git\bin\sh.exe")
    if not git_sh.exists():
        pytest.skip("Git sh is unavailable")
    operation = tmp_path / "operation"
    operation.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo = fake_bin / "sudo"
    sudo.write_text('#!/bin/sh\nif [ "$1" = -n ]; then shift; fi\nexec "$@"\n', encoding="utf-8")
    python3 = fake_bin / "python3"
    python3.write_text(
        f'#!/bin/sh\nexec "$(cygpath -u \'{pathlib.Path(os.sys.executable).as_posix()}\')" "$@"\n',
        encoding="utf-8",
    )
    subprocess.run(
        [str(git_sh), "-c", f"chmod 700 '{sudo.as_posix()}' '{python3.as_posix()}'"],
        check=True,
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    old = {
        "operation_id": "w29-c866f611-20260720T055453Z-c001bcd0", "utc_timestamp": "2026-07-20T00:00:00+00:00",
        "stage": "invocation_started", "status": "started", "launch_count": 0,
        "remote_shell_exit_code": None, "child_exit_code": None, "failure_category": None,
        "wrapper_source_revision": "old",
    }
    old_child = dict(old, stage="child_process_created", status="completed", launch_count=1)
    (operation / "grant-execution-evidence.jsonl").write_text(
        json.dumps(old) + "\n" + json.dumps(old_child) + "\n", encoding="utf-8"
    )
    for stage, status in (("invocation_started", "started"), ("local_validation_passed", "passed"), ("release_lock_released", "completed")):
        generated = render_operator_evidence(operation.as_posix(), stage, status)
        result = subprocess.run(
            [str(git_sh)], input=generated, cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=30, check=False,
        )
        assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in (operation / "grant-execution-evidence.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["stage"] for record in records[-3:]] == ["invocation_started", "local_validation_passed", "release_lock_released"]
    assert records[-1]["launch_count"] == 0
    allowed = {
        "operation_id", "utc_timestamp", "stage", "status", "launch_count",
        "remote_shell_exit_code", "child_exit_code", "failure_category",
        "wrapper_source_revision",
    }
    assert all(set(record) == allowed for record in records)
    serialized = json.dumps(records)
    assert "recipient" not in serialized and "DATABASE_URL" not in serialized


def _write_git_sh_command(path, python_source):
    python_file = path.with_suffix(".py")
    python_file.write_text(python_source, encoding="utf-8")
    path.write_text(
        f'#!/bin/sh\nexec "$(cygpath -u \'{pathlib.Path(os.sys.executable).as_posix()}\')" '
        f'"$(cygpath -w \'{python_file.as_posix()}\')" "$@"\n',
        encoding="utf-8",
    )


def _run_generated_grant_shell(tmp_path, mode):
    git_sh = pathlib.Path(r"C:\Program Files\Git\bin\sh.exe")
    if not git_sh.exists():
        pytest.skip("Git sh is unavailable")
    subprocess.run([
        str(git_sh), "-c",
        "rm -rf -- /tmp/community-w29-grant-w29-c866f611-20260720T055453Z-c001bcd0 "
        "/tmp/community-w29-capture-w29-c866f611-20260720T055453Z-c001bcd0",
    ], check=True)
    operation = tmp_path / "operation"
    operation.mkdir()
    for name, value in (("snapshot.json", "snapshot"), ("preview.json", "preview"), ("operation-manifest.json", "manifest")):
        (operation / name).write_text(value, encoding="utf-8")
    subprocess.run([str(git_sh), "-c", f"chmod 700 '{operation.as_posix()}'"], check=True)
    hashes = {
        name: __import__("hashlib").sha256((operation / name).read_bytes()).hexdigest()
        for name in ("snapshot.json", "preview.json", "operation-manifest.json")
    }
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    _write_git_sh_command(docker, textwrap.dedent(r'''
        import hashlib, json, os, pathlib, shutil, subprocess, sys
        a = sys.argv[1:]
        mode = os.environ.get('W29_FAKE_MODE', 'success')
        if a[0] == 'inspect':
            fmt = a[a.index('--format') + 1]
            value = 'running' if 'State.Status' in fmt else ('app:c866f611' if 'Config.Image' in fmt else ('sha256:image' if fmt == '{{.Image}}' else 'c866f611'))
            print('wrong' if mode == 'preflight_identity_mismatch' and fmt == '{{.Image}}' else value)
            raise SystemExit(0)
        if a[0] != 'exec': raise SystemExit(90)
        a = a[1:]
        if a and a[0] == '-i': a = a[1:]
        a = a[1:]
        if a[:2] == ['printenv', 'COMMUNITY_LEADERBOARD_REWARDS_ENABLED']: print('false'); raise SystemExit(0)
        if a[:2] == ['sh', '-c']: print('absent'); raise SystemExit(0)
        if a[0] == 'mkdir': pathlib.Path(a[-1]).mkdir(mode=0o700); raise SystemExit(0)
        if a[0] == 'tar':
            if mode == 'interrupted_remote_shell': raise SystemExit(130)
            raise SystemExit(subprocess.run(a, stdin=sys.stdin.buffer).returncode)
        if a[0] == 'sha256sum':
            p = pathlib.Path(a[1]); digest = hashlib.sha256(p.read_bytes()).hexdigest()
            print(('0' * 64 if mode == 'staged_hash_mismatch' else digest) + '  ' + str(p)); raise SystemExit(0)
        if a[0] == 'rm': shutil.rmtree(a[-1], ignore_errors=(mode != 'cleanup_failure')); raise SystemExit(88 if mode == 'cleanup_failure' else 0)
        if a[0] == 'test': raise SystemExit(0 if pathlib.Path(a[-1]).stat().st_size else 1)
        if a[0] == 'cat': sys.stdout.buffer.write(pathlib.Path(a[1]).read_bytes()); raise SystemExit(0)
        if a[0] == 'python':
            if mode in ('child_nonzero', 'interrupted_child'): raise SystemExit(74)
            if mode == 'process_creation_failure': raise SystemExit(127)
            snap = pathlib.Path(a[a.index('--snapshot-file') + 1])
            result = {
                'board_type': 'weekly', 'period_key': '2026-W29',
                'snapshot_sha256': 'canonical-snapshot', 'preview_sha256': 'canonical-preview',
                'result': 'committed', 'summary': {'claims_count': 21, 'component_count': 43,
                'total_coins': 4060, 'total_items': {'small_xp_potion': 25, 'xp_potion': 4},
                'total_badges': {'badge_lb_weekly_1': 1}},
            }
            if mode == 'identity_mismatch': result['period_key'] = '2026-W30'
            if mode == 'count_mismatch': result['summary']['claims_count'] = 20
            if mode == 'coin_mismatch': result['summary']['total_coins'] = 4059
            target = snap.parent / 'grant-result.json'
            target.write_text('{' if mode == 'malformed_json' else json.dumps(result), encoding='utf-8')
            if mode != 'empty_stdout': print('sanitized-child-complete')
            raise SystemExit(0)
        raise SystemExit(89)
    '''))
    sudo = fake_bin / "sudo"
    _write_git_sh_command(sudo, textwrap.dedent(r'''
        import hashlib, os, pathlib, shutil, subprocess, sys
        a = sys.argv[1:]
        if a and a[0] == '-n': a = a[1:]
        mode = os.environ.get('W29_FAKE_MODE', 'success')
        if mode == 'atomic_rename_failure' and a and a[0] == 'mv': raise SystemExit(83)
        if mode == 'temp_write_failure' and a and a[0] == 'tee': raise SystemExit(84)
        if a[0] == 'python3': raise SystemExit(subprocess.run([sys.executable] + a[1:], stdin=sys.stdin.buffer, stdout=sys.stdout.buffer, stderr=sys.stderr.buffer).returncode)
        if a[0] == 'sha256sum':
            p = pathlib.Path(a[1]); print(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p)); raise SystemExit(0)
        if a[0] == 'test': raise SystemExit(0 if (not pathlib.Path(a[-1]).exists() if '!' in a else pathlib.Path(a[-1]).exists()) else 1)
        if a[0] == 'tee': pathlib.Path(a[1]).write_bytes(sys.stdin.buffer.read()); raise SystemExit(0)
        if a[0] == 'chmod': os.chmod(a[-1], 0o600); raise SystemExit(0)
        if a[0] == 'mv': os.replace(a[1], a[2]); raise SystemExit(0)
        if a[0] == 'rm':
            for value in a:
                if not value.startswith('-'): pathlib.Path(value).unlink(missing_ok=True)
            raise SystemExit(0)
        if a[0] == 'tar': raise SystemExit(subprocess.run(a, stdin=sys.stdin.buffer, stdout=sys.stdout.buffer, stderr=sys.stderr.buffer).returncode)
        raise SystemExit(92)
    '''))
    stat = fake_bin / "stat"
    stat.write_text("#!/bin/sh\nif [ \"$2\" = %a ]; then echo 700; else echo root:root; fi\n", encoding="utf-8")
    python3 = fake_bin / "python3"
    python3.write_text(f'#!/bin/sh\nexec "$(cygpath -u \'{pathlib.Path(os.sys.executable).as_posix()}\')" "$@"\n', encoding="utf-8")
    subprocess.run([str(git_sh), "-c", f"chmod 700 '{docker.as_posix()}' '{sudo.as_posix()}' '{stat.as_posix()}' '{python3.as_posix()}'"], check=True)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["W29_FAKE_MODE"] = mode
    script = render_exact_w29_grant(operation.as_posix(), hashes["snapshot.json"], hashes["preview.json"], hashes["operation-manifest.json"])
    shell_prelude = ('stat(){ if [ "$2" = "%a" ]; then echo 700; else echo root:root; fi; }\n'
                     'mkdir(){ command mkdir -p "$3"; }\n')
    result = subprocess.run([str(git_sh)], input=shell_prelude + script, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, check=False)
    evidence_path = operation / "grant-execution-evidence.jsonl"
    evidence = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()] if evidence_path.exists() else []
    return result, evidence, operation


def test_generated_remote_shell_launches_exactly_one_real_synthetic_child_and_persists_result(tmp_path):
    result, evidence, operation = _run_generated_grant_shell(tmp_path, "success")
    assert result.returncode == 0, result.stderr
    assert (operation / "grant-result.json").exists()
    assert max(record["launch_count"] for record in evidence) == 1
    assert sum(record["stage"] == "child_process_created" and record["status"] == "completed" for record in evidence) == 1
    assert any(record["stage"] == "result_persisted" and record["status"] == "completed" for record in evidence)


@pytest.mark.parametrize("mode", ["preflight_identity_mismatch", "staged_hash_mismatch", "interrupted_remote_shell"])
def test_generated_remote_shell_prelaunch_failures_record_zero_launches(tmp_path, mode):
    result, evidence, operation = _run_generated_grant_shell(tmp_path, mode)
    assert result.returncode != 0
    assert max(record["launch_count"] for record in evidence) == 0
    assert not any(record["stage"] == "child_process_created" for record in evidence)
    assert any(record["status"] == "failed" for record in evidence)
    assert not (operation / "grant-result.json").exists()


@pytest.mark.parametrize("mode", [
    "child_nonzero", "interrupted_child", "process_creation_failure", "empty_stdout", "malformed_json",
    "identity_mismatch", "count_mismatch", "coin_mismatch", "temp_write_failure",
    "atomic_rename_failure", "cleanup_failure",
])
def test_generated_remote_shell_failures_are_durable_single_launch_and_fail_closed(tmp_path, mode):
    result, evidence, operation = _run_generated_grant_shell(tmp_path, mode)
    assert result.returncode != 0
    assert max(record["launch_count"] for record in evidence) == 1
    assert sum(record["stage"] == "child_process_created" and record["status"] == "completed" for record in evidence) == 1
    assert any(record["status"] == "failed" for record in evidence)
    if mode == "cleanup_failure":
        assert (operation / "grant-result.json").exists()
        assert any(record["stage"] == "result_persisted" and record["status"] == "completed" for record in evidence)
        assert any(record["stage"] == "cleanup_completed" and record["status"] == "failed" for record in evidence)
    else:
        assert not (operation / "grant-result.json").exists()
    assert "recipient" not in json.dumps(evidence)


@pytest.mark.parametrize("mode", [
    "zero_state_nonzero", "ssh_transport_failure", "lock_release_failure",
    "main_transport_failure", "main_transport_evidence_failure",
])
def test_wrapper_preflight_transport_and_lock_release_failures_are_ordered_and_fail_closed(tmp_path, mode):
    release = tmp_path / "scripts" / "release"
    release.mkdir(parents=True)
    wrapper = release / GRANT.name
    wrapper.write_text(source(GRANT), encoding="utf-8")
    event_file = tmp_path / "events.txt"
    fake_release = release / "ReleaseTooling.psm1"
    fake_release.write_text(textwrap.dedent(r'''
        function Assert-OwnerGate { param($Provided,$Expected) if($Provided -ne $Expected){throw 'gate'} }
        function Resolve-RepoPath { param($Path) return $env:W29_REPO_ROOT }
        function Get-ReleaseLayout { param($Path) return [pscustomobject]@{compose_directory='/release';ssh_alias='fake';scheduler_service_name='scheduler'} }
        function Add-Event { param($Value) Add-Content -LiteralPath $env:W29_EVENT_FILE -Value $Value }
        function Enter-RemoteReleaseOperationLock { Add-Event 'lock_acquired'; return @{} }
        function Exit-RemoteReleaseOperationLock {
            Add-Event 'lock_release_called'
            if($env:W29_WRAPPER_MODE -eq 'lock_release_failure'){throw 'sanitized lock release failure'}
            return @{}
        }
            function Invoke-RemoteShellCommand {
            param($SshAlias,$Name,$ScriptText)
                Add-Event ($Name + '|' + $ScriptText)
                if($Name -eq 'community_w29_evidence_child_launch_started' -and $env:W29_WRAPPER_MODE -eq 'main_transport_evidence_failure'){throw 'sanitized evidence append failure'}
            if($Name -eq 'community_w29_exact_grant_zero_state'){
                if($env:W29_WRAPPER_MODE -eq 'ssh_transport_failure'){throw 'sanitized transport failure'}
                if($env:W29_WRAPPER_MODE -eq 'zero_state_nonzero'){return [pscustomobject]@{exit_code=33;stdout='';stderr='withheld'}}
                return [pscustomobject]@{exit_code=0;stdout='';stderr=''}
            }
                if($Name -eq 'community_w29_exact_grant'){
                    if($env:W29_WRAPPER_MODE -like 'main_transport*'){throw 'primary main grant transport failure'}
                    return [pscustomobject]@{exit_code=74;stdout='';stderr='withheld'}
                }
            return [pscustomobject]@{exit_code=0;stdout='';stderr=''}
        }
        Export-ModuleMember -Function *
    '''), encoding="utf-8")
    fake_community = release / "CommunityRewardsExecutionControl.psm1"
    fake_community.write_text(textwrap.dedent(r'''
        function New-CommunityRewardsGrantEvidenceRemoteScript { param($OperationDirectory,$OperationId,$Stage,$Status,$LaunchCount,$WrapperSourceRevision,$RemoteShellExitCode,$FailureCategory) return "evidence:${Stage}:${Status}:${LaunchCount}:${RemoteShellExitCode}:${FailureCategory}" }
        function New-CommunityRewardsZeroStateProbeRemoteScript { param($SchedulerContainer) return 'zero-probe' }
        function New-CommunityRewardsExactW29GrantRemoteScript {
            param($SchedulerContainer,$ExpectedSchedulerImageTag,$ExpectedSchedulerImageId,$ExpectedRevision,$OperationDirectory,$OperationId,$SnapshotFileSha256,$PreviewFileSha256,$ManifestFileSha256,$CanonicalSnapshotSha256,$CanonicalPreviewSha256,$WrapperSourceRevision)
            return 'grant-script'
        }
        Export-ModuleMember -Function *
    '''), encoding="utf-8")
    env = os.environ.copy()
    env.update({"W29_WRAPPER_MODE": mode, "W29_EVENT_FILE": str(event_file), "W29_REPO_ROOT": str(ROOT)})
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper),
        "-OperationId", "w29-c866f611-20260720T055453Z-c001bcd0",
        "-ExpectedSchedulerImageTag", "go-odyssey-app:11a16674",
        "-ExpectedSchedulerImageId", "sha256:3dc3209ea45d497ec2e913486200ebeb7895f82c12c0c41fbbdfad859ed353c2",
        "-ExpectedRevision", "11a1667491afab89b9957ced2f17d4b6904da6e9",
        "-CanonicalSnapshotSha256", "4c7aa3ea6d9c477fe34951054d89ecb2c11e6f2bac925142c06e1c44beff7740",
        "-CanonicalPreviewSha256", "449f33defce8a134990f61448316a9bf4e3ceae8e75f0a803fb1822aa1f8d0dc",
        "-Execute", "-OwnerGate", "GO_GRANT_W29",
    ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode != 0
    assert event_file.exists(), result.stderr
    events = event_file.read_text(encoding="utf-8").splitlines()
    assert any(item.startswith("community_w29_evidence_remote_preflight_started|") for item in events)
    assert "lock_release_called" in events
    if mode == "lock_release_failure":
        assert sum(item.startswith("community_w29_exact_grant|") for item in events) == 1
        assert any(
            item.startswith("community_w29_evidence_release_lock_released|")
            and "release_lock_released:failed" in item
            and item.endswith(":release_lock")
            for item in events
        )
    elif mode.startswith("main_transport"):
        assert sum(item.startswith("community_w29_exact_grant|") for item in events) == 1
        assert any(
            item.startswith("community_w29_evidence_child_launch_started|")
            and "child_launch_started:failed:0::remote_shell" in item
            for item in events
        )
        assert "primary main grant transport failure" in result.stderr
        assert "sanitized evidence append failure" not in result.stderr
        assert any(item.startswith("community_w29_evidence_release_lock_released|") for item in events)
    else:
        assert not any(item.startswith("community_w29_exact_grant|") for item in events)
    assert "recipient" not in result.stdout.lower()


@pytest.mark.parametrize(
    "failure_marker",
    [
        "remote_preflight_started", "child_command_prepared", "child_launch_started",
        "child_process_created", "child_exit_received", "result_read_started",
        "result_parsed", "result_validated", "result_persisted", "cleanup_started",
    ],
)
def test_exact_w29_failure_stages_are_durable_and_fail_closed(failure_marker):
    script = render_exact_w29_grant()
    assert failure_marker in script
    assert 'record_stage "$CURRENT_STAGE" failed' in script
    assert "grant-execution-evidence.jsonl" in script
    assert "set -x" not in script
    assert "DATABASE_URL" not in script


def test_exact_w29_grant_is_bound_to_authorized_operation_and_totals():
    combined = source(MODULE) + source(GRANT)
    for identity in (
        "w29-c866f611-20260720T055453Z-c001bcd0",
        "4c7aa3ea6d9c477fe34951054d89ecb2c11e6f2bac925142c06e1c44beff7740",
        "449f33defce8a134990f61448316a9bf4e3ceae8e75f0a803fb1822aa1f8d0dc",
        "53c256c5517e4e9bfa9a1eaf80beeb910eb3a329cbfb3780072d7c2cb76b91cc",
        "8cefc8925b5b142c0e58f10ce04cd2d723102e9c554e1f2332240d63080ab0fa",
        "6d42e5bc7ac7c0494df3492fd480201a20b523ee2884b410edbdd2fc919b752d",
        "--expected-claim-count 21",
        "--expected-component-count 43",
        "--expected-total-coins 4060",
        "small_xp_potion",
        "xp_potion",
        "badge_lb_weekly_1",
    ):
        assert identity in combined


def test_exact_w29_grant_wrapper_is_execute_and_owner_gated_with_release_lock():
    wrapper = source(GRANT)
    assert "if (-not $Execute)" in wrapper
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_GRANT_W29'" in wrapper
    assert "Enter-RemoteReleaseOperationLock" in wrapper
    assert "Exit-RemoteReleaseOperationLock" in wrapper
    assert "Invoke-RemoteShellCommand" in wrapper
    assert "recipient-level remote output withheld" in wrapper
    assert "Invoke-BoundedSshCommand" not in wrapper
    zero_state = wrapper.index("New-CommunityRewardsZeroStateProbeRemoteScript")
    grant_script = wrapper.index("New-CommunityRewardsExactW29GrantRemoteScript")
    assert wrapper.index("Enter-RemoteReleaseOperationLock") < zero_state < grant_script


def test_exact_w29_grant_cleanup_is_exact_and_does_not_touch_reward_logic():
    script = render_exact_w29_grant()
    assert 'rm -rf -- "$CONTAINER_OPERATION_DIRECTORY"' in script
    assert 'rm -f -- "$RESULT_TEMP_FILE"' in script
    assert "grant-result.json.tmp" in script
    assert "leaderboard_reward_claims" not in script
    assert "INSERT " not in script
    assert "UPDATE " not in script
    assert "DELETE " not in script


def test_exact_w29_grant_without_execute_fails_before_remote_access():
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(GRANT),
            "-OperationId", "w29-c866f611-20260720T055453Z-c001bcd0",
            "-ExpectedSchedulerImageTag", "go-odyssey-app:11a16674",
            "-ExpectedSchedulerImageId", "sha256:3dc3209ea45d497ec2e913486200ebeb7895f82c12c0c41fbbdfad859ed353c2",
            "-ExpectedRevision", "11a1667491afab89b9957ced2f17d4b6904da6e9",
            "-CanonicalSnapshotSha256", "4c7aa3ea6d9c477fe34951054d89ecb2c11e6f2bac925142c06e1c44beff7740",
            "-CanonicalPreviewSha256", "449f33defce8a134990f61448316a9bf4e3ceae8e75f0a803fb1822aa1f8d0dc",
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode != 0
    assert "Exact W29 grant requires -Execute" in result.stderr
    assert "ssh" not in result.stderr.lower()


def test_exact_w29_grant_wrapper_rejects_obsolete_image_identity():
    """Regression for the stale-ValidateSet gap found after the 2026-07-21
    controlled deployment to go-odyssey-app:11a16674: the wrapper's own
    parameter validation must reject the now-obsolete c866f611 identity
    outright, before any Execute/OwnerGate/SSH logic ever runs."""
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(GRANT),
            "-OperationId", "w29-c866f611-20260720T055453Z-c001bcd0",
            "-ExpectedSchedulerImageTag", "go-odyssey-app:c866f611",
            "-ExpectedSchedulerImageId", "sha256:e8bafcd1bce435f78782e220f82058112e930c71dcaea6a87ff0adb2462a8ac3",
            "-ExpectedRevision", "c866f6114232839c2951d02c71f000983098eda6",
            "-CanonicalSnapshotSha256", "4c7aa3ea6d9c477fe34951054d89ecb2c11e6f2bac925142c06e1c44beff7740",
            "-CanonicalPreviewSha256", "449f33defce8a134990f61448316a9bf4e3ceae8e75f0a803fb1822aa1f8d0dc",
            "-Execute", "-OwnerGate", "GO_GRANT_W29",
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode != 0
    assert "ssh" not in result.stderr.lower()


def test_exact_w29_grant_wrapper_is_bound_to_current_deployed_image_identity():
    wrapper = source(GRANT)
    for identity in (
        "go-odyssey-app:11a16674",
        "sha256:3dc3209ea45d497ec2e913486200ebeb7895f82c12c0c41fbbdfad859ed353c2",
        "11a1667491afab89b9957ced2f17d4b6904da6e9",
    ):
        assert identity in wrapper
    for obsolete in (
        "go-odyssey-app:c866f611",
        "sha256:e8bafcd1bce435f78782e220f82058112e930c71dcaea6a87ff0adb2462a8ac3",
        "c866f6114232839c2951d02c71f000983098eda6",
    ):
        assert obsolete not in wrapper
