# RPG V1 Wave2 Onboarding V2 Handoff

Status: `HANDOFF_ONLY_NOT_IN_SCOPE`

This document is the product handoff for a later onboarding redesign. It is
not part of the RPG V1 legacy Newbie Quest retirement behavior and does not
authorize Wave2 gameplay/content admission.

## Locked requirements

1. A new player understands what to do within 60 seconds.
2. Show a short Welcome cinematic.
3. Provide a clear **Start First Adventure** CTA.
4. Teach the sequence challenge → combat/result → progression.
5. Use contextual teaching instead of presenting every lesson at once.
6. Show the Shop tutorial only when Shop is genuinely usable.
7. Show the equipment tutorial on the first meaningful equipment acquisition.
8. Show the Boss tutorial at the first Boss encounter.
9. Support skipping the onboarding.
10. Support replay/help after onboarding.
11. Do not depend on the legacy Newbie Quest Stage 1–7 architecture.
12. The Driver Tour may survive as optional interface help.

## Architectural and release constraints

- The current RPG V1 newcomer path must remain independent of
  `newbie_quest_state`, `newbie_quest_tasks`, `newbie_quest_events`, legacy
  spotlight storage, and legacy Newbie Quest rewards.
- The server remains authoritative for challenge results, combat/result state,
  progression, unlocks, rewards, Spirit, equipment, and any Boss outcome.
- A contextual lesson may explain or point to an already-valid current action;
  it must not grant authority or make Shop, payment, equipment, or Boss state
  available by presentation alone.
- Welcome/cinematic state must be independently idempotent and replay-safe.
- Driver Tour remains manually available where its current selectors and routes
  are valid; it is never a prerequisite for gameplay.
- Wave2 must carry its own deterministic first-run, returning-player, skip,
  replay/help, and refresh/relogin coverage before admission.

## Legacy compatibility retained during the handoff

The retirement leaves historical local and server state dormant. No client
cleanup or destructive migration is authorized for these identifiers:

- `cg_newbie_quest_v1[:uid]`
- `nq_spotlight_s1..s7_shown/skipped`
- `nq_map_quiz_done`
- `nq_daily_training_done`
- `newbie_quest_state`, `newbie_quest_tasks`, and `newbie_quest_events`
- `user_stats.tutorial_step`
- `adventure_intro_seen_v1` when present in an older account/client

The current client does not read, write, or mount the retired NQ UI. Historical
keys remain untouched so an older client can continue to interpret them, and
the server compatibility endpoints fail closed for retired accounts.

## Required future acceptance

Before Wave2 implementation is admitted, the Owner must lock the exact source
SHA and verify the current canonical gameplay destination, then accept the
new-account, returning-account, skip/replay, authority, reward-idempotency,
Shop-default-off, payment/revenue-default-off, device, and static/SW release
contracts. Legacy database/history cleanup remains a separate post-acceptance
decision and is not implied by this handoff.
