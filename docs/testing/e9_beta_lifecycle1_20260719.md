# E9-BETA-LIFECYCLE1 Lifecycle Hardening

Status: development validation only (no Production access or deployment).

## Lifecycle inventory

| Surface | Implementation | Cleanup/guard | Coverage | Risk |
|---|---|---|---|---|
| Shell root | `#e9-adventure-shell` and five slot roots | `destroyShell()` restores Legacy, clears slot state and resets mount generation | Node shell tests | VERIFIED |
| Fragment listeners | World-stage tile/CTA and nav/dock handlers | Registered through `E9.on()` and removed on destroy | Node remount/listener test | VERIFIED |
| Document listeners | Component-loaded listeners are installed once when scripts load | Not installed per mount; component-specific i18n listeners use `E9.on()` | Existing shell/component tests | SAFE |
| Timers | No E9 component timer is currently allocated | No timer cleanup required in current implementation | Source audit | SAFE |
| Observers | No E9 Mutation/Resize/IntersectionObserver is currently allocated | No observer cleanup required in current implementation | Source audit | SAFE |
| Async sources | Component loader and adapter fetches | Generation check prevents stale promise callbacks from mutating DOM or recovering a newer shell | Stale in-flight mount test and component contracts | VERIFIED |

## Changes

- Added a generation-scoped lifecycle registry to `js/e9/shell.js`.
- Added `destroyShell`/`unmountShell`, `E9.on`, cleanup registration and a
  current-generation predicate.
- `component_loader.js` now carries the generation on the loaded event and
  ignores stale success/failure callbacks.
- World stage, HUD, cards, dock and nav handlers now register cleanup and guard
  asynchronous DOM updates.
- Destroying a shell returns ownership to Legacy and permits a clean remount.

The change does not alter eligibility, rollout policy, API contracts, judging,
player state, Shadow, or gameplay behavior.

## Risk matrix

| Area | Result | Evidence |
|---|---|---|
| Duplicate init/mount | VERIFIED | Existing idempotence test plus clean-remount test |
| Listener leakage | VERIFIED | Registered handlers are removed by `destroyShell()` |
| Timer leakage | SAFE | No timers in E9 component sources |
| Observer leakage | SAFE | No observers in E9 component sources |
| Stale async updates | VERIFIED | In-flight mount completion is ignored after destroy |
| Legacy/E9 exclusivity | VERIFIED | Existing exclusivity suite remains green |
| Session remount | VERIFIED | Destroy then init mounts a fresh generation |

## Validation

- `python -m pytest tests/test_e9_adventure_shell_foundation.py tests/test_e9_adventure_shell_integration.py tests/test_e9_shell_exclusivity.py tests/test_e9_c3_core_navigation.py -q` — 119 passed.
- `node tests/e9_node_tests/run_shell_exclusivity_tests.js` — 8 passed.
- `git diff --check` — passed.
- Playwright E2E contracts were not runnable in this checkout because
  `playwright-core` is not installed; no code was changed to bypass that
  environment limitation.

## Safety

No Production login, SSH, deployment, container recreation, flag mutation,
Shadow change, database/SGF/questions change, or player-state mutation was
performed. The pre-existing untracked `secret_key.txt` in this isolated
worktree was not accessed or staged.
