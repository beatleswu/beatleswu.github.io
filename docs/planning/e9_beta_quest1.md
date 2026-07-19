# E9-BETA-QUEST1 — Read-Only Main and Daily Quest Board

Status: development-only, not deployed.

## Verified data contract

| Data | Canonical source/adapter | Use | Decision |
|---|---|---|---|
| Daily completion | `GET /api/daily-challenge/today`, `ActivityState.fetchDailyChallenge`, `user_submitted` | Boolean daily quest | Included |
| Zone stars | `AdventureState.fetchAdventureState`, normalized `zones[].stars` | Maximum stars | Included |
| Completed zones | `zones[].cleared` derived from canonical `status === completed` | First boss/zone completion | Included |
| Profile level | `PlayerState.normalizeProfile` | Lifetime level quest | Deferred; no need to add another fetch in QUEST1 |
| SRS due | `GET /api/srs/due`, `count` | Outstanding due work, not completion | Excluded |
| Weekly activity | No reliable per-user period counter | Weekly progression | Explicitly excluded |
| `challenge_wins`, `corrected` | Present in raw sources but not established as a stable quest contract | Lifetime optional quests | Excluded pending audit |

No new endpoint, persistence, write behavior, reward, or scheduler behavior was
required.

## Quest catalog

| ID | Category | Source | Target | CTA |
|---|---|---|---:|---|
| `main.earn_first_zone_star` | main | `adventure.maxStars` | 1 | Adventure |
| `main.complete_three_star_zone` | main | `adventure.maxStars` | 3 | Adventure |
| `main.defeat_first_boss` | main | `adventure.completedZoneCount` | 1 | Adventure |
| `daily.complete_daily_challenge` | daily | `dailyChallenge.userSubmitted` | 1 | Daily Challenge |

IDs are stable semantic identities. Definitions contain no reward, claim, or
grant fields. Weekly quests are not displayed.

## Evaluator and snapshot contract

`js/e9/quest_evaluator.js` is a deterministic pure evaluator. It performs no
fetch, DOM mutation, storage write, navigation, or player mutation. Missing,
malformed, negative, or unknown values return `unavailable` rather than a
fabricated zero or completion.

`js/e9/quest_store.js` creates a per-mount normalized snapshot from the existing
Adventure and Daily adapters. It keeps no persistent state, reuses adapter
in-flight/cache behavior, records partial source errors, and clears snapshot,
transition memory, and adapter caches during lifecycle destruction.

## Lifecycle and animation

The board uses the existing E9 generation contract (`isLifecycleCurrent`,
`registerCleanup`, and `E9.on`). Stale responses do not render or animate.
Completion animation is represented only by the in-memory `justCompleted`
transition marker: initial completed state, refresh/remount, logout/re-login,
and account changes do not replay historical completion.

## UI and accessibility

The board is mounted inside the existing Right Cards component boundary. It has
Main/Daily tabs, loading and partial-error status, unavailable/in-progress/
completed badges, accessible progress elements, keyboard-operable buttons, and
canonical links to Adventure or Daily Challenge. There is no claim control or
reward copy. Styling is responsive and uses the existing E9 responsive shell.

## Deferred

- Weekly period identity and persistence: QUEST2.
- Completion ledger, claim contract, and reset semantics: QUEST2.
- Coins/XP/items and grants: QUEST3.
- Additional content and seasonal/weekly quests: QUEST4.
