# P0 Lane B — Authenticated Adventure Acceptance

## Acceptance contract

The supported normal-player path is:

```text
World Map
  → Continue Adventure
  → Adventure question pool is bound
  → Map Battle V1 attempt/nonce accepted under global
  → canonical zone/question identity is retained
  → answer is judged server-side
  → settlement creates mbv1 progression evidence
  → distinct Adventure progress increments once
```

No client grade, admin session claim, Practice API, or presentation fallback
can create the progression credit.

## Executable cases

| ID | Setup / action | Expected result | Evidence |
|---|---|---|---|
| A01 | authenticated non-admin, mode `global`, enter Adventure | attempt accepted; no admin claim needed | `test_global_mode_remains_available_without_admin_status` |
| A02 | authenticated admin, mode `global`, enter Adventure | attempt accepted | `test_global_mode_admits_authoritative_admin_without_session_privilege_claim` |
| A03 | authenticated non-admin, mode `admin` | `403 map_battle_mode_not_eligible`; no battle mutation | existing admin-mode rejection tests |
| A04 | authenticated DB admin, mode `admin` | attempt and answer admitted | existing `test_admin_mode_uses_authoritative_db_status...` |
| A05 | anonymous, any non-off mode | canonical `401 未登入`; no attempt/battle row | `test_anonymous_map_battle_attempt_preserves_canonical_login_boundary` |
| A06 | `global`, non-admin, correct move | server result `CORRECT`; review source begins `mbv1:`; progression `applied` | `test_global_non_admin_adventure_answer_progresses_once_and_replays_safely` |
| A07 | replay the exact settled answer | authoritative duplicate; progression `duplicate`; one review/progress row | same test plus existing duplicate tests |
| A08 | `global`, non-admin, wrong move | server result `INCORRECT`; evidence is retained; no correct progression increment | existing `test_legacy_correct_duplicate_incorrect_and_invalid_are_authoritative` |
| A09 | answer after failed Map Battle initialization | no Practice/legacy review request; visible unavailable state | Node client contract + source guard |
| A10 | ordinary Practice correct/wrong answer | remains `practice`; existing Practice policy remains non-progress-bearing | source contract and existing SRS tests |
| A11 | first-clear/settlement replay | no new reward settlement is introduced by this lane | existing Adventure first-clear and Map Battle duplicate tests |

## End-to-end result

The new API integration case begins with an authenticated session representing
the Continue Adventure handshake. It proves the progression-bearing server path
rather than only calling `mode_eligible()`:

```text
GLOBAL_NON_ADMIN_END_TO_END_PROGRESS_PASS=YES
TARGET_MODE=global
SERVER_VERDICT=CORRECT
CANONICAL_EVIDENCE=mbv1:<server_submission_id>
PROGRESSION_FIRST_SUBMISSION=applied
REPLAY_PROGRESSION=duplicate
REVIEW_ROW_COUNT_AFTER_REPLAY=1
```

The client entry source also proves that same-page and reload/re-entry paths
populate the Adventure question pool before `loadQuestion()`, preserving the
origin through Map Battle initialization.

## Negative path result

When Map Battle is unavailable, the client does not answer the question. It
sets the lifecycle to blocked, disables battle actions, publishes a diagnostic,
and displays an explicit unavailable message. The rejected request path is not
converted to `SRS.practiceAnswer()` or a public legacy `SRS.review()` call.

## Reward boundary

This lane does not add reward logic. Existing server Map Battle settlement and
first-clear/duplicate guards remain the only reward authorities. The new lane
tests only assert that its failure guard does not create a second settlement or
reward call.

## Test execution

```text
pytest -q tests/test_p0_lane_b_adventure_forward_repair.py
10 passed

pytest -q tests/test_map_battle_legacy_adapter.py tests/test_map_battle_runtime.py tests/test_e10_review_transport_v1b.py tests/test_e10_battle_scene_presentation_and_auto_next.py tests/deployment/test_map_battle_configuration_wiring.py -k "not real_container"
103 passed, 1 deselected

pytest -q tests/test_adventure_correct_progress_lord_gate.py tests/test_adventure_first_clear_reward.py tests/test_adventure_boss_finish_server_authoritative.py -k "not real_container"
82 passed
```

The single deselected test is the optional direct-container probe requiring an
external configured release image; it is not a hidden application test.
