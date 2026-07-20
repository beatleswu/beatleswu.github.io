Set-StrictMode -Version Latest

$script:CommunityFlag = 'COMMUNITY_LEADERBOARD_REWARDS_ENABLED'

function Get-CommunityRewardsFrozenComposePrefix {
    return "COMMUNITY_LEADERBOARD_REWARDS_ENABLED='false'"
}

function New-CommunityRewardsZeroStateProbeRemoteScript {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$SchedulerContainer)
    if ([string]::IsNullOrWhiteSpace($SchedulerContainer) -or $SchedulerContainer.Contains("`n") -or $SchedulerContainer.Contains("`r")) {
        throw 'Scheduler container identity must be a nonblank single-line value.'
    }
    $scheduler = Quote-PosixShellArgument $SchedulerContainer
    return @"
set -eu
docker exec -i $scheduler python - <<'__COMMUNITY_ZERO_STATE__'
import json, os, zlib
import psycopg
conn=psycopg.connect(os.environ['DATABASE_URL'])
try:
    with conn.cursor() as cur:
        def one(sql, args=()): cur.execute(sql,args); return int(cur.fetchone()[0])
        result={}
        for period in ('2026-W29','2026-W30'):
            result[period]={
              'claims':one('SELECT count(*) FROM leaderboard_reward_claims WHERE board_type=%s AND period_key=%s',('weekly',period)),
              'snapshots':one('SELECT count(*) FROM leaderboard_snapshots WHERE board_type=%s AND period_key=%s',('weekly',period)),
              'components':one('SELECT count(*) FROM leaderboard_reward_component_log l JOIN leaderboard_reward_claims c ON c.id=l.claim_id WHERE c.board_type=%s AND c.period_key=%s',('weekly',period)),
            }
        ns=zlib.crc32(b'community_leaderboard_rewards') & 0x7fffffff
        scope=zlib.crc32(b'weekly:2026-W29') & 0x7fffffff
        result['w29_lock']=one("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted AND classid=%s AND objid=%s",(ns,scope))
    if any(result[p][k] for p in ('2026-W29','2026-W30') for k in ('claims','snapshots','components')) or result['w29_lock']:
        raise SystemExit(33)
    print(json.dumps(result,sort_keys=True))
finally: conn.close()
__COMMUNITY_ZERO_STATE__
"@
}

function New-CommunityRewardsFreezeRemoteScript {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$SchedulerContainer,
        [Parameter(Mandatory = $true)][string]$AppContainer,
        [Parameter(Mandatory = $true)][string]$ExpectedSchedulerImageId,
        [Parameter(Mandatory = $true)][string]$ExpectedSchedulerImageTag,
        [Parameter(Mandatory = $true)][string]$ComposeDirectory,
        [Parameter(Mandatory = $true)][string]$ComposeProject,
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [Parameter(Mandatory = $true)][string]$EnvFile,
        [Parameter(Mandatory = $true)][string]$SchedulerService,
        [Parameter(Mandatory = $true)][string]$ComposeEnvironmentPrefix
    )
    foreach ($value in $PSBoundParameters.Values) {
        if ([string]::IsNullOrWhiteSpace([string]$value) -or ([string]$value).Contains("`n") -or ([string]$value).Contains("`r")) {
            throw 'Community freeze parameters must be nonblank single-line values.'
        }
    }
    $template = @'
set -eu
SCHEDULER=__SCHEDULER__
APP=__APP__
EXPECTED_IMAGE_ID=__EXPECTED_IMAGE_ID__
EXPECTED_IMAGE_TAG=__EXPECTED_IMAGE_TAG__
COMPOSE_DIRECTORY=__COMPOSE_DIRECTORY__
COMPOSE_PROJECT=__COMPOSE_PROJECT__
COMPOSE_FILE=__COMPOSE_FILE__
ENV_FILE=__ENV_FILE__
SCHEDULER_SERVICE=__SCHEDULER_SERVICE__

test "$(docker inspect "$SCHEDULER" --format '{{.State.Status}}')" = running
test "$(docker inspect "$SCHEDULER" --format '{{.Image}}')" = "$EXPECTED_IMAGE_ID"
test "$(docker inspect "$SCHEDULER" --format '{{.Config.Image}}')" = "$EXPECTED_IMAGE_TAG"
test "$(docker inspect "$SCHEDULER" --format '{{index .Config.Labels "com.docker.compose.project"}}')" = "$COMPOSE_PROJECT"
test "$(docker inspect "$SCHEDULER" --format '{{index .Config.Labels "com.docker.compose.service"}}')" = "$SCHEDULER_SERVICE"

sudo -n python3 - "$ENV_FILE" <<'__COMMUNITY_CONFIGURED_VALUE__'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
if not p.is_file() or p.is_symlink(): raise SystemExit(31)
values=[]
for raw in p.read_bytes().splitlines():
    if raw.startswith(b"COMMUNITY_LEADERBOARD_REWARDS_ENABLED="):
        values.append(raw.split(b"=",1)[1].strip().lower())
if values != [b"true"]: raise SystemExit(32)
print('{"configured":"true"}')
__COMMUNITY_CONFIGURED_VALUE__

test "$(docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = true
docker exec -i "$SCHEDULER" python - <<'__COMMUNITY_ZERO_STATE__'
import json, os, zlib
import psycopg
conn=psycopg.connect(os.environ['DATABASE_URL'])
try:
    with conn.cursor() as cur:
        def one(sql, args=()):
            cur.execute(sql,args); return int(cur.fetchone()[0])
        result={}
        for period in ('2026-W29','2026-W30'):
            result[period]={
              'claims':one('SELECT count(*) FROM leaderboard_reward_claims WHERE board_type=%s AND period_key=%s',('weekly',period)),
              'snapshots':one('SELECT count(*) FROM leaderboard_snapshots WHERE board_type=%s AND period_key=%s',('weekly',period)),
              'components':one('SELECT count(*) FROM leaderboard_reward_component_log l JOIN leaderboard_reward_claims c ON c.id=l.claim_id WHERE c.board_type=%s AND c.period_key=%s',('weekly',period)),
            }
        ns=zlib.crc32(b'community_leaderboard_rewards') & 0x7fffffff
        scope=zlib.crc32(b'weekly:2026-W29') & 0x7fffffff
        result['w29_lock']=one("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted AND classid=%s AND objid=%s",(ns,scope))
    if any(result[p][k] for p in ('2026-W29','2026-W30') for k in ('claims','snapshots','components')) or result['w29_lock']:
        raise SystemExit(33)
    print(json.dumps(result,sort_keys=True))
finally:
    conn.close()
__COMMUNITY_ZERO_STATE__

docker stop "$SCHEDULER" >/dev/null
test "$(docker inspect "$SCHEDULER" --format '{{.State.Status}}')" = exited
test "$(docker inspect "$SCHEDULER" --format '{{.Image}}')" = "$EXPECTED_IMAGE_ID"
docker exec -i "$APP" python - <<'__COMMUNITY_POST_STOP_ZERO_STATE__'
import json, os, zlib
import psycopg
conn=psycopg.connect(os.environ['DATABASE_URL'])
try:
    with conn.cursor() as cur:
        def one(sql, args=()):
            cur.execute(sql,args); return int(cur.fetchone()[0])
        result={}
        for period in ('2026-W29','2026-W30'):
            result[period]={
              'claims':one('SELECT count(*) FROM leaderboard_reward_claims WHERE board_type=%s AND period_key=%s',('weekly',period)),
              'snapshots':one('SELECT count(*) FROM leaderboard_snapshots WHERE board_type=%s AND period_key=%s',('weekly',period)),
              'components':one('SELECT count(*) FROM leaderboard_reward_component_log l JOIN leaderboard_reward_claims c ON c.id=l.claim_id WHERE c.board_type=%s AND c.period_key=%s',('weekly',period)),
            }
        ns=zlib.crc32(b'community_leaderboard_rewards') & 0x7fffffff
        scope=zlib.crc32(b'weekly:2026-W29') & 0x7fffffff
        result['w29_lock']=one("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted AND classid=%s AND objid=%s",(ns,scope))
    if any(result[p][k] for p in ('2026-W29','2026-W30') for k in ('claims','snapshots','components')) or result['w29_lock']:
        raise SystemExit(34)
    print(json.dumps(result,sort_keys=True))
finally:
    conn.close()
__COMMUNITY_POST_STOP_ZERO_STATE__

cd "$COMPOSE_DIRECTORY"
__COMPOSE_PREFIX__ COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false docker compose -p "$COMPOSE_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-build --no-deps --force-recreate "$SCHEDULER_SERVICE"
test "$(docker inspect "$SCHEDULER" --format '{{.State.Status}}')" = running
test "$(docker inspect "$SCHEDULER" --format '{{.Image}}')" = "$EXPECTED_IMAGE_ID"
test "$(docker inspect "$SCHEDULER" --format '{{.Config.Image}}')" = "$EXPECTED_IMAGE_TAG"
test "$(docker inspect "$SCHEDULER" --format '{{.RestartCount}}')" = 0
test "$(docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = false
printf '%s\n' '{"operation":"freeze","effective":"false","old_image_preserved":true,"zero_state_verified":true}'
'@
    $replacements = [ordered]@{
        '__SCHEDULER__' = Quote-PosixShellArgument $SchedulerContainer
        '__APP__' = Quote-PosixShellArgument $AppContainer
        '__EXPECTED_IMAGE_ID__' = Quote-PosixShellArgument $ExpectedSchedulerImageId
        '__EXPECTED_IMAGE_TAG__' = Quote-PosixShellArgument $ExpectedSchedulerImageTag
        '__COMPOSE_DIRECTORY__' = Quote-PosixShellArgument $ComposeDirectory
        '__COMPOSE_PROJECT__' = Quote-PosixShellArgument $ComposeProject
        '__COMPOSE_FILE__' = Quote-PosixShellArgument $ComposeFile
        '__ENV_FILE__' = Quote-PosixShellArgument $EnvFile
        '__SCHEDULER_SERVICE__' = Quote-PosixShellArgument $SchedulerService
        '__COMPOSE_PREFIX__' = $ComposeEnvironmentPrefix
    }
    foreach ($item in $replacements.GetEnumerator()) { $template = $template.Replace($item.Key, $item.Value) }
    return $template
}

function New-CommunityRewardsResumeRemoteScript {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$SchedulerContainer,
        [Parameter(Mandatory = $true)][string]$AppContainer,
        [Parameter(Mandatory = $true)][string]$ExpectedSchedulerImageId,
        [Parameter(Mandatory = $true)][string]$ExpectedSchedulerImageTag,
        [Parameter(Mandatory = $true)][string]$ComposeDirectory,
        [Parameter(Mandatory = $true)][string]$ComposeProject,
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [Parameter(Mandatory = $true)][string]$EnvFile,
        [Parameter(Mandatory = $true)][string]$SchedulerService,
        [Parameter(Mandatory = $true)][string]$ComposeEnvironmentPrefix
    )
    $freeze = New-CommunityRewardsFreezeRemoteScript @PSBoundParameters
    $resumeMarker = 'test "$(docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = true'
    $resume = $freeze.Substring(0, $freeze.IndexOf($resumeMarker))
    $resume += @'
test "$(docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = false
docker exec -i "$SCHEDULER" python - <<'__COMMUNITY_SETTLED_STATE__'
import json, os
import psycopg
conn=psycopg.connect(os.environ['DATABASE_URL'])
try:
    with conn.cursor() as cur:
        def one(sql,args=()): cur.execute(sql,args); return int(cur.fetchone()[0])
        claims=one('SELECT count(*) FROM leaderboard_reward_claims WHERE board_type=%s AND period_key=%s',('weekly','2026-W29'))
        unsettled=one("SELECT count(*) FROM leaderboard_reward_claims WHERE board_type=%s AND period_key=%s AND status <> 'granted'",('weekly','2026-W29'))
        w30_claims=one('SELECT count(*) FROM leaderboard_reward_claims WHERE board_type=%s AND period_key=%s',('weekly','2026-W30'))
        w30_snapshots=one('SELECT count(*) FROM leaderboard_snapshots WHERE board_type=%s AND period_key=%s',('weekly','2026-W30'))
        w30_components=one('SELECT count(*) FROM leaderboard_reward_component_log l JOIN leaderboard_reward_claims c ON c.id=l.claim_id WHERE c.board_type=%s AND c.period_key=%s',('weekly','2026-W30'))
    if claims <= 0 or unsettled or w30_claims or w30_snapshots or w30_components: raise SystemExit(41)
    print(json.dumps({'w29_claims':claims,'w29_unsettled':unsettled,'w30_claims':w30_claims,'w30_snapshots':w30_snapshots,'w30_components':w30_components},sort_keys=True))
finally: conn.close()
__COMMUNITY_SETTLED_STATE__
cd "$COMPOSE_DIRECTORY"
__COMPOSE_PREFIX__ docker compose -p "$COMPOSE_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-build --no-deps --force-recreate "$SCHEDULER_SERVICE"
test "$(docker inspect "$SCHEDULER" --format '{{.State.Status}}')" = running
test "$(docker inspect "$SCHEDULER" --format '{{.Image}}')" = "$EXPECTED_IMAGE_ID"
test "$(docker inspect "$SCHEDULER" --format '{{.Config.Image}}')" = "$EXPECTED_IMAGE_TAG"
test "$(docker inspect "$SCHEDULER" --format '{{.RestartCount}}')" = 0
test "$(docker exec "$SCHEDULER" printenv COMMUNITY_LEADERBOARD_REWARDS_ENABLED)" = true
printf '%s\n' '{"operation":"resume","effective":"true","image_preserved":true,"w29_settled":true}'
'@
    $resume = $resume.Replace('__COMPOSE_PREFIX__', $ComposeEnvironmentPrefix)
    return $resume
}

Export-ModuleMember -Function @(
    'Get-CommunityRewardsFrozenComposePrefix',
    'New-CommunityRewardsZeroStateProbeRemoteScript',
    'New-CommunityRewardsFreezeRemoteScript',
    'New-CommunityRewardsResumeRemoteScript'
)
