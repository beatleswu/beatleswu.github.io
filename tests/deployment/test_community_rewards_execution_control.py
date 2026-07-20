import pathlib
import subprocess
import textwrap
import os

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


def render_exact_w29_grant():
    command = (
        f"Import-Module '{ROOT / 'scripts/release/ReleaseTooling.psm1'}' -Force -DisableNameChecking; "
        f"Import-Module '{MODULE}' -Force -DisableNameChecking; "
        "New-CommunityRewardsExactW29GrantRemoteScript "
        "-SchedulerContainer scheduler -ExpectedSchedulerImageTag app:c866f611 "
        "-ExpectedSchedulerImageId sha256:image -ExpectedRevision c866f611 "
        "-OperationDirectory /operations/w29 -OperationId w29-c866f611-20260720T055453Z-c001bcd0 "
        "-SnapshotFileSha256 snapshot-file -PreviewFileSha256 preview-file "
        "-ManifestFileSha256 manifest-file -CanonicalSnapshotSha256 canonical-snapshot "
        "-CanonicalPreviewSha256 canonical-preview"
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
        "test \"$(docker exec \"$SCHEDULER\" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)\" = true",
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
    assert 'GRANT_OUTPUT="$(docker exec "$SCHEDULER" python ' in script
    assert 'test -n "$GRANT_OUTPUT"' in script
    assert "unset GRANT_OUTPUT" in script
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
    assert 'GRANT_OUTPUT="$(docker exec' in render_exact_w29_grant()


def test_exact_w29_grant_validates_before_child_launch_and_persists_atomically():
    script = render_exact_w29_grant()
    launch = script.index('GRANT_OUTPUT="$(docker exec')
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
            "-ExpectedSchedulerImageTag", "go-odyssey-app:c866f611",
            "-ExpectedSchedulerImageId", "sha256:e8bafcd1bce435f78782e220f82058112e930c71dcaea6a87ff0adb2462a8ac3",
            "-ExpectedRevision", "c866f6114232839c2951d02c71f000983098eda6",
            "-CanonicalSnapshotSha256", "4c7aa3ea6d9c477fe34951054d89ecb2c11e6f2bac925142c06e1c44beff7740",
            "-CanonicalPreviewSha256", "449f33defce8a134990f61448316a9bf4e3ceae8e75f0a803fb1822aa1f8d0dc",
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode != 0
    assert "Exact W29 grant requires -Execute" in result.stderr
    assert "ssh" not in result.stderr.lower()
