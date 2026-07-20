import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/release/CommunityRewardsExecutionControl.psm1"
DEPLOY = ROOT / "scripts/release/deploy-release-image.ps1"
ROLLBACK = ROOT / "scripts/release/rollback-release.ps1"
RESUME = ROOT / "scripts/release/resume-community-leaderboard-rewards.ps1"
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
        "-ExpectedSchedulerImageTag app:old -ComposeDirectory /release -ComposeProject project "
        "-ComposeFile /release/docker-compose.release.yml -EnvFile /protected/.env "
        "-SchedulerService scheduler -ComposeEnvironmentPrefix \"GO_ODYSSEY_IMAGE='app:old' QUESTIONS_CONTENT_VOLUME_NAME='go-data'\""
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


def test_changed_powershell_files_parse():
    paths = (MODULE, DEPLOY, ROLLBACK, RESUME)
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


def test_freeze_remote_contract_has_zero_race_order_and_old_image_preservation():
    script = render("freeze")
    ordered = (
        "test \"$(docker inspect \"$SCHEDULER\" --format '{{.Image}}')\" = \"$EXPECTED_IMAGE_ID\"",
        "values != [b\"true\"]",
        "test \"$(docker exec \"$SCHEDULER\" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)\" = true",
        "result['w29_lock']",
        "docker stop \"$SCHEDULER\"",
        "--format '{{.State.Status}}')\" = exited",
        "docker exec -i \"$APP\" python - <<'__COMMUNITY_POST_STOP_ZERO_STATE__'",
        "raise SystemExit(34)",
        "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false docker compose",
        "--force-recreate \"$SCHEDULER_SERVICE\"",
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


def test_default_deploy_path_remains_conditional_and_requires_normal_gate():
    text = source(DEPLOY)
    assert "if ($FreezeCommunityLeaderboardRewards)" in text
    assert "else { 'GO_DEPLOY' }" in text
    assert "else { 'unchanged' }" in text
    assert "[switch]$FreezeCommunityLeaderboardRewards" in text


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
