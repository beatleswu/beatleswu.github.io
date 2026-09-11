# GO Odyssey ACT-A App Wiring D1 — Activation Call-Site Map

Status: ACT-A coordinator infrastructure is implemented.  The exact reviewed
ACT-B, ACT-D, and the ACT-E dark onboarding bridge are integrated into
`app.py`; the accepted ACT-C R1 Rewards Sync authority is wired, while Friend
Challenge settlement remains held for the separately governed schema.  No
migration is applied by this task.

This is an exact source-level inventory of `app.py` in the D1 worktree.  Line
references identify the current source locations; they are not Production
runtime evidence.  The baseline is `BASE_HEAD=da531c6da0edabab3c025823ec1157e604d56498`.

## Authority and transaction boundary

ACT-A owns the HTTP/session adapter and the request transaction boundary.
Provider, reward, inventory, and onboarding decisions remain in their owning
domain modules.  An Activation domain receives the already-open `conn` from
`_activation_transaction()` at `app.py:3369` and must not call `commit()`,
`rollback()`, or open an independent write transaction.  The coordinator
commits once on success, rolls back on domain or commit failure, and closes
the connection.

`ActivationDomainResult` and `ActivationDomainError` in
`activation_http_contract.py` are Flask-free typed values.  The app adapters
at `app.py:3403`, `:3410`, and the ACT-C coin-error adapter at `:3417`
serialize only domain-owned status/body fields and stable error fields.
Existing route-specific Map Battle, Shop, Companion, and Review mappers remain
in place.  The ACT-B adapter maps provider-contract failures to the existing
`JudgeUnavailable`/Map Battle HTTP mapper; ACT-C maps typed reward errors to a
controlled 400/503 response; ACT-D maps typed insufficient stock to the
existing boolean/`not_owned` contract.

## Map Battle provider, restoration, and settlement — ACT-B boundary

| Concern | `app.py` call site | Domain/provider call sites | Transaction/error handling |
| --- | --- | --- | --- |
| Provider creation and battle restoration | `map_battle_v1_prepare_attempt()` `:15562`; adapters `_map_battle_provider_for_new()` `:15333` and `_map_battle_provider_for_restore()` `:15349` | Provider restore `:15622`; provider creation `:15630`; provider-bound `create_map_battle()`/metadata persistence `:15639-15648`; legacy Zone 3 and fallback creation `:15659-15690`; attempt issuance `:15698`; authoritative reload `:15715` | One explicit `_activation_transaction()` at `:15598`; ACT-B contract failures become `JudgeUnavailable`; existing selector and Map Battle error semantics remain. |
| Resume validation | `map_battle_v1_resume_validation()` `:15754`; provider restore `:15794` | `validate_resumable_attempt()` `:15783`; provider resolution revalidates the persisted binding before public state | Explicit coordinator at `:15781`; existing `MapBattleRuntimeError` mapper remains. |
| Provider resolution during answer settlement | `_map_battle_f010_profile()` `:15363`; `_map_battle_monster_profile_resolver()` `:15412` | Existing compatibility resolver remains the explicit legacy adapter; `settle_answer()` receives `MAP_BATTLE_RUNTIME_PROVIDER_REGISTRY` at `:15904` and uses the same ACT-B boundary | Settlement failures remain the existing `_map_battle_error_response()` contract. |
| Answer settlement | `map_battle_v1_answers()` `:15877` | `settle_answer()` `:15895-15905`, with server-owned question, combat, Monster profile, runtime-provider, and Spirit projection adapters | Explicit coordinator at `:15893`; no route-level commit/rollback. |
| Submission nonce mutation | `map_battle_v1_submission_nonce()` `:15846` | `issue_submission_nonce_for_attempt()` `:15858` | Explicit coordinator at `:15856`; typed Map Battle errors keep current payload/status. |
| Post-settlement progression | `_run_map_battle_progression()` `:17457`, invoked after settlement at `:15931` | `MapBattleReviewHandoff.apply()` `:17474` remains the existing settle-then-progress handoff | The settlement transaction is committed by ACT-A before the progression call; D1 preserves this ordering and does not refactor `_srs_review_operation` or introduce another partial-commit path. |
| Read-only stale reload | `map_battle_v1_battle_state()` `:15816` | `load_authoritative_battle_state()` `:15827` | Existing read path retained; no business or HTTP change. |

The current Map Battle feature gate remains request-time/admin-controlled. D1
does not change `E10_MAP_BATTLE_V1_MODE`, rollout state, selector flags, or
any Production feature flag.

## Reward and coin mutation map — ACT-C boundary

| Concern | `app.py` call site | Current authority and handoff status |
| --- | --- | --- |
| Quest completion read projection | `_stage_completion_state()` `:17804`; `/api/quest-board` `quest_board_state()` `:17845`; progress route `:18025` | Read-only identity folding. The reward writer explicitly uses `fold_identity=False`; Puzzle Identity behavior is unchanged. |
| Reward sync | `/api/rewards/sync`, `rewards_sync()` `:17950` | Calls accepted ACT-C R1 `settle_rewards_sync_claim_in_transaction()` at `:17971` inside `_activation_transaction()` `:17955`; ACT-C owns claim idempotency, cap policy, coin balance, and currency ledger. ACT-A updates XP and clears winning quest rows in the same transaction at `:18004-18008`; typed ACT-C errors map at `:18011`. Friend Challenge remains held for schema; no migration is applied. |
| Quest runtime coin adapter | `_quest_v2_reward_authorities().grant_coins()` `:3722`; `_grant_coins()` call `:3729` | Existing app authority binding; no ACT-C route cutover is claimed. |
| Monster settlement coin writer | Nested `grant_coins()` `:8176`; `_grant_coins()` call `:8179` | Existing Monster-specific daily gate delegates to `_grant_coins()`; no new reward policy is added by ACT-A. |
| Daily quest writers | `_update_daily_quests()` `:8777`; `_grant_coins()` calls `:8836`, `:8889` | Direct existing app reward writers; no C handoff integrated. |
| Newbie checkpoint coin reward | `newbie_quest_checkpoint()` `:10008`; `_grant_coins()` `:10033` | Current app-owned onboarding/reward coupling; ACT-E/C handoff is not available for this path. |
| Friend Challenge reward settlement | `_award_challenge_reward()` `:23202`; `friend_challenge_answer()` `:23324`; direct combined XP/coin update `:23259-23271`; invocation `:23385-23392`; commit `:23417` | Held for schema. Existing app-owned XP/coin, pet, badge, and result authority remains unchanged. ACT-C's settlement helper is not wired, and the stale `friend_challenge_reward_settlement_v1.py` migration is absent from this branch; no legacy unlogged fallback is introduced. |
| Generic coin writer | `_grant_coins()` `:24498`; `_spend_coins()` `:24519` | Existing currency ledger/balance writers. D1 maps these callers but does not duplicate or broadly move them. |
| Shop fragment fallback | `shop_use()` `_grant_coins()` call `:26102` | Existing refund behavior remains inside the Shop caller; no reward policy is moved into ACT-A. |
| Admin coin adjustment | `admin_set_coins()` `:10936`; direct balance/log writes `:10948-10953` | Admin-only maintenance path, outside the public ACT-C handoff. Feature state is unchanged. |
| Canonical Shop purchase | `_canonical_shop_purchase_response()` `:25031`; request transaction `:25050`; typed purchase calls `:25073`, `:25087`; commit/error mapper `:25102`, `:25108-25114` | Existing C019/C026 Shop authority and mapper retained; no purchase or enablement wiring. |

## Inventory consumption map — ACT-D boundary

`_inv_consume()` is defined at `app.py:24540` and now delegates to
`consume_shop_inventory()` from the exact ACT-D handoff.  It catches only the
typed insufficient-stock result so the two existing callers preserve their
prior external behavior:

1. `ai_explain()` (`POST /api/explain`, `app.py:11172`) consumes
   `ai_explain_ticket` at `:11197` and keeps the existing caller commit.
2. `shop_use()` (`POST /api/shop/use`, `app.py:25862`) consumes the requested
   item at `:26049`, including the existing savepoint/replay handling and
   caller-owned commits at `:25935`, `:26036`, `:26068`, `:26291`, and `:26306`.

`_inv_add()` and the legacy Shop/item-use helpers remain outside the D1 move
boundary.  ACT-D owns the guarded decrement and never commits or rolls back;
the route remains the transaction coordinator.

## Onboarding, newbie quest, and eligibility map — ACT-E boundary

| Concern | `app.py` call site | Current behavior |
| --- | --- | --- |
| ACT-E V2 projection and transitions | Authenticated routes `:6062-6116`; `_onboarding_v2_mutation()` `:3508`; schema/transaction guard `:3447`, `:3513-3523` | `GET /api/onboarding/v2` calls `get_onboarding_v2_state()` at `:6077`; POST start/resume/skip/finish adapt the reviewed authority at `:6098`, `:6104`, `:6110`, `:6116`. The route is dark by default and never applies the candidate schema. Existing canonical `SKIPPED`/`skip()` policy is wired only behind the dark gate. |
| Eligibility/read projection | `_newbie_quest_snapshot()` `:9802`; `auth_me()` (`GET /api/auth/me`) `:9855` | Reads `onboarding_required`, `onboarding_path`, `newbie_quest_state`, and `tour_done`; computes `needs_onboarding_choice` and `newbie_quest_eligible`. |
| Tour completion | `auth_tour_done()` `POST /api/auth/tour_done` `:9941-9947` | Writes `user_stats.tour_done`; existing app transaction. |
| Newbie quest view/snapshot | `auth_newbie_quest()` `POST/GET /api/auth/newbie_quest` `:9952-9971` | Calls snapshot, optionally logs view, and commits existing state. |
| Task progress | `newbie_quest_progress()` `POST /api/newbie_quest/progress` `:9976-10003` | Checks eligibility/prerequisite, completes task, and commits existing state. |
| Checkpoint/reward | `newbie_quest_checkpoint()` `POST /api/newbie_quest/checkpoint` `:10008-10061` | Checks eligibility/prerequisite, completes task, grants current coins/items/title, and commits. |
| Path selection | `onboarding_choice()` `POST /api/user/onboarding_choice` `:10066-10101` | Validates and locks `newbie`/`test`; preserves race-conflict response semantics. |
| Placement eligibility | `set_placement_elo()` `POST /api/user/set_placement_elo` `:10124-10164` | Writes provisional Elo/rank and applies existing Adventure unlock cap. |
| Account creation seed | `auth_register()` `:9234`, seed transaction around `:9247`; `auth_google_login()` `:9383`, seed transaction around `:9410` | Seeds `onboarding_required=1`; no D1 change. |

No V2 onboarding enablement or feature rollout is performed.  ACT-E's
authenticated route surface remains dark by default; the existing legacy
Newbie Quest routes are unchanged.

## Puzzle Identity contract

The LC019-W2 reader path remains behaviorally unchanged. `_identity_group_key_map()`
still probes table availability, checks `BootstrapGatedIdentityReader.hot`,
returns the legacy bijection without querying when cold/unavailable, and calls
`reader.group_keys_for(ids)` only when the bootstrap is hot and the tables are
present. D1 corrects stale comments that treated the resolver as permanently
dormant; it does not alter identity reads, writes, resolver inputs, or
question content.

## Handoff protocol and availability

Before applying an ACT-B/C/D/E wiring change, ACT-A verifies the exact reviewed
source branch, commit, and tree, inspects the domain contract, and applies only
the required route diff. A handoff that requires `app.py` to repeat provider,
reward, inventory, or onboarding decisions is rejected back to its owning
lane. The integrated handoffs are:

| Lane | Verified source | App wiring |
| --- | --- | --- |
| ACT-B | `codex/act-b-provider-boundary-d1-001`, `abce846a3edd202849b2e2dc6dc6cd9200d26bf1`, tree `0f4a96287fc8154f4e4ae79ac3da2ff19179dea4` | Provider creation, restore, and settlement registry seam only. |
| ACT-C | `codex/act-c-reward-authority-d1-001`, `c7f4b7b3b389f5769671dc3de7a8effe0174597a`, tree `40d9a434dd2fd1c236ce942eb1c0fb1b0d3d69fd` | Accepted R1 `coin_reward_authority.py`, reward tests, and PostgreSQL concurrency evidence carried exactly; Rewards Sync wiring only. Friend Challenge settlement remains held for schema, with no migration or unsafe fallback. |
| ACT-D | `codex/act-d-inventory-authority-d1-001`, `b02281a77b164cab2af9c957fdd050b0267086bd`, tree `b5f178ce47ea1d1a90efc9f75f31f471e9aaca35` | `_inv_consume()` delegates the guarded decrement and preserves legacy caller mapping. |
| ACT-E | `codex/act-e-onboarding-v2-d1-001`, `b34c9617021fa27b70afe7ab1fb52fca9daf783d`, tree `ace2b94b4d364a2f309c0d711ced606e7be39f0c` | Dark-gated authenticated projection/start/resume/skip/finish routes; no V2 schema application or `index.html`/`sw.js` wiring. |

No `index.html` or `sw.js` wiring is required by the reviewed handoffs.  No
migration, schema application, flag change, Production mutation, merge, or
deploy is part of D1.

## Packaging handoff to ACT-F

The Dockerfile uses an explicit root-module `COPY` list and
`deploy/build-manifest.json` repeats the curated build-input and post-build
verification lists.  The current ACT-A runtime imports are not all present in
those lists.  ACT-F must add and verify these exact files in its packaging
scope; ACT-A does not edit the packaging files:

| Runtime file | Why it is required |
| --- | --- |
| `activation_http_contract.py` | Imported by `app.py` for typed Activation result/error adaptation. |
| `coin_reward_authority.py` | Imported by `app.py` for accepted ACT-C R1 Rewards Sync settlement. |
| `shop_inventory_authority.py` | Imported by `app.py` for the ACT-D guarded inventory decrement. |
| `wave2_onboarding_authority.py` | Imported by `app.py` for the dark V2 projection and transition routes. |

`onboarding_v2_transition.py` is inspected but is not an `app.py` runtime
import in this candidate; it is used by the ACT-E transition tests/documented
handoff and therefore does not by itself require an app-image copy.  Existing
`adventure_monster_runtime_contract.py`, `map_battle_runtime.py`, and
`map_battle_persistence.py` are already listed.  Exact request:

`ACT_F_BUILD_PACKAGING_REQUEST = add the four app-imported runtime files above
to Dockerfile and deploy/build-manifest.json, with matching post-build
verification/provenance entries where required; do not package the deleted
ACT-C migration or copy migrations/ wholesale.`
