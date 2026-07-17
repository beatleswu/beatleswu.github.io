# Shadow Event Envelope V4

Status: implementation contract for SGF Engine V1 closure (2026-07-17)

This contract supersedes `shadow-v3` for newly emitted events. The v1 and v3
documents remain historical mixed-stream references. Legacy judging remains
authoritative; every field below is diagnostic-only and
`user_facing_judgement_changed` must remain `false`.

## Required envelope

| Field | Type | Null | Contract |
|---|---|---:|---|
| `schema_version` | string | no | Exact value `shadow-v4`. |
| `event_id` | UUID string | no | Unique event identity used for rotated-file deduplication. |
| `created_at` | RFC 3339 string | no | UTC observation timestamp. |
| `route` | string | no | Normalized answer route. |
| `request_id` | string | no | Bounded request/correlation identifier. |
| `entry_point` | string | no | Registry entry-point key. |
| `legacy_question_id` | integer/string | yes | Legacy alias only; never canonical identity. |
| `canonical_puzzle_id` | UUID v4 string | yes | Read-only alias lookup result; never derived from SGF or legacy ID. |
| `invalid_identity` | boolean | no | `true` when the alias is absent, invalid, ambiguous, or lookup fails. |
| `session_id` | string | yes | Bounded route context; not an identity source. |
| `transform_idx` | integer | yes | Geometric transform index supplied by the route. |
| `player_color` | `B`, `W`, or null | yes | Null unless reliably derivable from the transformed answer tree. |
| `player_move_sgf` | string or null | yes | First actual move, for example `B[sf]`; never synthesized. |
| `player_move_board_coordinate` | string or null | yes | First actual move in GTP-style board form, for example `T14`. |
| `source_judgement` | string | no | Legacy `accept`, `reject`, or `unknown`. |
| `legacy_reason` | string or null | yes | Sanitized stable reason when the Legacy path exposes one; otherwise null. |
| `legacy_unknown` | boolean | no | True only when the Legacy result itself is unavailable. |
| `client_judgement` | string | no | Client claim, or `unknown`; never authoritative. |
| `shadow_judgement` | string | no | SGF Engine observation only. |
| `shadow_reason` | string | no | Sanitized SGF Engine diagnostic reason. |
| `classification` | string | no | Legacy/Shadow or candidate class below. |
| `candidate_only_detected` | boolean | no | True only for a proven transformed candidate outside the accepted SGF path. |
| `candidate_source` | string or null | yes | Exactly `accepted_moves`, `katago_best_move`, or null. |
| `gf003_related` | boolean | no | Identity-only relationship; never inferred from coordinates/candidates. |
| `parser_status` | string | no | `ok` or `failed`. |
| `parser_failure_reason` | string | no | Empty on success; bounded reason on failure. |
| `exception_class` | string | no | Empty unless SGF Engine/import/evaluation failed. |
| `exception_message` | string | no | Sanitized and bounded; never includes credentials. |
| `latency_ms` | non-negative integer | no | Shadow observation latency. |
| `moves_count` | non-negative integer | no | Number of actual player moves evaluated. |
| `review_recommended` | boolean | no | Diagnostic queue hint only. |
| `owner_decision_required` | boolean | no | Diagnostic governance hint only. |
| `user_facing_judgement_changed` | boolean | no | Invariant: always `false`. |

Unavailable route context is encoded as null. V4 never guesses player color,
move, canonical identity, or Legacy reason. In particular, a route that sends
only a correctness boolean produces `missing canonical moves`; Shadow does not
manufacture a success/rejection path from that boolean.

## Candidate-equivalent classes

Candidate detection uses the first actual player move. Stored candidates are
transformed into the presented board orientation before comparison. It runs in
the shared adapter and never changes the Legacy branch, response, persistence,
reward, SRS, progress, quota, or player message.

`legacy_accepts_shadow_candidate_match` (Class A):

- Legacy accepted.
- SGF Engine returned `reject` or `off_tree`.
- The move matches a transform-adjusted candidate source.
- `candidate_only_detected=true` and `candidate_source` names that source.
- Dashboard reports this separately from unexplained disagreement.

`legacy_rejects_transform_candidate` (Class B):

- Legacy rejected.
- SGF Engine returned `reject` or `off_tree`.
- Correct transformation proves the move matches a candidate source.
- It remains a disagreement and is counted as the known Legacy transform bug.
- It must not be absorbed into Class A or counted as agreement.

An SGF Engine error/unsupported result cannot prove candidate-only status, and
a move already accepted by the SGF tree is not candidate-only. If both sources
match, `accepted_moves` has deterministic diagnostic precedence.

The known Legacy `accepted_moves` comparison bug is intentionally unchanged.
V4 detects and measures it; Shadow must not imitate it and must not repair the
player-visible result in this V1 task.

## GF-003 boundary

`gf003_related=true` requires equality between a valid resolved
`canonical_puzzle_id` and the owner-governed GF-003 canonical UUID. It must not
be inferred from `B[sf]`, `B[sd]`, KataGo, or `accepted_moves` evidence.

Owner truth remains unchanged:

- Canonical: Black T14 / SGF `B[sf]`
- Candidate equivalent: Black T16 / SGF `B[sd]`

GF-003 override remains disabled. The candidate is observation data only.

## Mixed-stream dashboard

Readers must accept v3 and v4 concurrently. Missing v4 fields in a v3 record
normalize to null (unknown), not false. Aggregates expose schema distribution,
Class A, Class B, known-Legacy-bug, and candidate-source counts separately.
Old or partial records cannot raise an Admin request exception.

Aggregate reads include the active file and retained rotations, deduplicate by
`event_id`, scan newest first, and publish byte/event/truncation metadata. A
partial read window must never be labelled as a complete agreement window.

## Identity resolution

The owner-confirmed ADR-021 alias key is
`(record_index, legacy_question_id)`. Exact composite lookup has precedence.
When a legacy route carries only `legacy_question_id`, the alias table may
resolve it only if exactly one row has that ID; zero or multiple rows fail
closed. No route, gameplay mode, ordering, filename, or SGF/content value may
break an ambiguity.

Missing, ambiguous, invalid, or failed lookup emits
`canonical_puzzle_id=null`, `invalid_identity=true`, and
`gf003_related=false`. Player request paths are read-only and no request-time
alias creation is permitted. Production migration and backfill remain pending
a separate owner gate.
