# E10 B023 Companion operation authority

Status: implementation candidate; Production migration and enablement are
not included.

## Authority boundary

`companion_operations` is the single business-correctness authority for
these state-changing operations:

* `SPIRIT_UNLOCK`
* `SPIRIT_FEED`
* `SPIRIT_TRAIN`
* `SPIRIT_SWITCH`
* `SPIRIT_EVOLVE`

Its semantic identity is `(user_id, operation_id)`. The server validates the
authenticated user, operation family, target Spirit, policy version, and a
canonical SHA-256 payload hash. The client may propose an operation ID, but
it cannot define ownership, result, progression, quantity, or reward.

The terminal states are `COMPLETED` and deterministic `FAILED`. A
transactional infrastructure exception rolls the reservation back; it is
never recorded as a successful result.

## Replay contract

The first request reserves a `PENDING` row, performs the authoritative
mutation, writes lineage/evidence, stores the HTTP response envelope, and
commits all state together. A retry with the same user, operation ID, family,
target, policy, and canonical payload returns the stored response without
running the mutation callback. A changed canonical payload returns HTTP 409.
A committed unexpected `PENDING` row fails closed rather than being retried
by a second worker.

## Route contract

The integrated routes accept an optional caller-owned `operation_id` and
return the server-bound operation ID in the original response:

| Route | Operation | Canonical intent |
| --- | --- | --- |
| `/api/pet/choose` | `SPIRIT_UNLOCK` | starter Spirit identity |
| `/api/pet/unlock` | `SPIRIT_UNLOCK` | target Spirit |
| `/api/pet/feed` | `SPIRIT_FEED` | active Spirit, food key, quantity `1` |
| `/api/pet/interact` with `mode=train` | `SPIRIT_TRAIN` | active Spirit, mode, normalized hours |
| `/api/pet/switch` | `SPIRIT_SWITCH` | target owned Spirit |

`/api/pet/interact` with `mode=pet` and `/api/pet/rename` remain the existing
low-value presentation/interaction paths; they are not one of the five
canonical B023 operation families. No public evolve route is added here.

## D5 boundaries

Feed reserves and completes D5C `ITEM_USE` with the same caller operation
identity, while `pet_inventory` remains the legacy resource authority and is
decremented conditionally with `qty > 0`. D5A `ITEM_ACQUISITION` and
`ITEM_CONSUME_EFFECT` events are appended in the caller transaction as
evidence/lineage only. Neither outbox events nor analytics authorize a
mutation.

`commit_evolution_transition(conn, ...)` is the D008 domain handoff. It
accepts server-derived current/next levels and source policy, rechecks the
authoritative Spirit state, rejects direct multi-stage jumps, persists one
`spirit_evolution_events` transition, and uses the same Companion operation
replay contract. It does not choose progression thresholds or alter balance.

## Additive schema and release order

Migration candidates:

* `migrations/companion_operations_v1.py`
* `migrations/spirit_evolution_events_v1.py`

Both are caller-commit migrations and are intentionally not invoked by app
startup. The current app can run while the additive tables exist. The B023
routes return a fail-closed unavailable response if their authority table is
absent. The governed release order is:

`apply additive migrations` → `deploy/enable the B023-compatible app`.

Production migration, deploy, payment, revenue, equipment, combat, Monster,
and Spirit effect runtime changes are outside B023.
