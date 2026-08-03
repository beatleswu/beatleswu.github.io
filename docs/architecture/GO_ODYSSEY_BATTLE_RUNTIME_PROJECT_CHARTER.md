# Go Odyssey Battle Runtime — Project Charter

```
Charter Version: 1.0.0
Date:            2026-08-03
Status:          Active
Supersedes:      None
```

---

## 1. Executive Summary

The Battle Runtime is the single server-authoritative service that decides the outcome of
every player answer submitted from a Go Odyssey battle surface, and the only component
permitted to change battle state as a result.

It is a **domain service**, not a feature of any particular map. Legacy Adventure, the E10
World Map, and every future battle surface (Guild, Boss, Raid) are **adapters** that supply
context to the Runtime and render what it returns. They are not permitted to compute
outcomes of their own.

This Charter is the engineering contract that governs the Runtime. It is not a description
of the current implementation and not a record of how the implementation was produced. Where
the current code and this Charter disagree, that disagreement is a defect to be resolved —
either by correcting the code or by formally revising this Charter (§21).

The three properties this Charter exists to protect, in priority order:

1. **Correctness of authority** — the server decides; the client displays.
2. **Exactly-once settlement** — a retried answer never applies damage twice.
3. **Boundary stability** — new battle surfaces cost adapter work, not Runtime work.

---

## 2. Historical Background

Battle damage was originally computed on the client. The browser graded the player's answer,
derived damage locally, and reported the outcome to a spaced-repetition review endpoint that
existed for an unrelated purpose — recording study progress. That endpoint had no concept of
a battle, no battle state to protect, and no reason to reject an implausible result.

This produced three classes of defect that could not be fixed within that design:

- **Authority defects.** Any client could report any outcome. Correctness was advisory.
- **Idempotency defects.** A network retry re-applied damage, because nothing identified two
  transmissions as the same logical answer.
- **State-drift defects.** Battle HP existed only in browser memory. A reload, a second tab,
  or a transport failure produced a battle state no server could reconstruct or arbitrate.

The Battle Runtime replaces that arrangement. Battle state is persisted server-side, answers
are judged server-side against authoritative question content, and settlement is applied
atomically under a versioned concurrency protocol. The review endpoint retains its original
spaced-repetition purpose and is no longer part of any damage path.

---

## 3. Problem Statement

A battle surface must be able to ask: *"the player submitted these moves — what happens?"*
and receive an answer that is correct, final, and identical no matter how many times the
question is asked.

Satisfying that requires resolving four problems simultaneously:

| Problem | Requirement |
|---|---|
| Who decides the outcome? | A single server-side judge over authoritative content. |
| What identifies a submission? | A server-issued token bound to owner, battle, and attempt. |
| What happens on concurrent writes? | Serialised state transition with an explicit conflict result. |
| What happens on repeated delivery? | The original settled result is replayed, never recomputed. |

A design that solves any three of these and not the fourth is not acceptable. In particular,
server-side judging without idempotency still corrupts battle state under ordinary mobile
network conditions.

---

## 4. Architecture Goals

1. **Server authority is total.** No client input influences grade, damage, or HP.
2. **Surface-agnostic core.** The Runtime has no knowledge of which map invoked it.
3. **Deterministic settlement.** Identical inputs against identical server state produce an
   identical outcome.
4. **Fail-closed.** Every ambiguity — unknown feature mode, unavailable judge, malformed
   metadata — resolves to "no settlement," never to a permissive default.
5. **Additive persistence.** Schema evolution adds; it does not rewrite existing battle rows.
6. **Auditability.** Every settlement leaves durable evidence of before-state, after-state,
   result, and the revision it advanced.
7. **Extensibility without core change.** A new battle surface is a new adapter.

---

## 5. System Architecture

```
                    ┌─────────────────────────────┐
                    │        Presentation         │
                    │  board, HP bars, animation  │
                    └──────────────┬──────────────┘
                                   │  renders authoritative state
                    ┌──────────────┴──────────────┐
                    │           Adapters          │
                    │  Legacy · E10 · (future)    │
                    │  transport + context only   │
                    └──────────────┬──────────────┘
                                   │  battle context
                    ┌──────────────┴──────────────┐
                    │        Battle Runtime       │
                    │  protocol · authority ·     │
                    │  judge adapter · damage     │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │         Persistence         │
                    │  schema · locking · CAS     │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │      Canonical Judging      │
                    │  authoritative SGF engine   │
                    └─────────────────────────────┘
```

**Dependency direction is one-way and non-negotiable.** Adapters depend on the Runtime. The
Runtime depends on Persistence and the canonical judging engine. The Runtime must not import,
reference, branch on, or special-case any adapter, surface, or presentation concern.

The Runtime must remain free of web-framework imports. It is invoked from within a request
handler's transaction; it does not own routing, sessions, or the transaction boundary.

---

## 6. Runtime Lifecycle

```
  battle context (zone, question)
            │
            ▼
  create or resume battle          ── server sets HP, revision, ownership
            │
            ▼
  issue attempt                    ── server binds question identity, board,
            │                          colour, transform, judge version, TTL
            ▼
  issue submission nonce           ── raw value returned exactly once
            │
            ▼
  render question                  ── presentation only
            │
            ▼
  submit answer + same nonce
            │
            ▼
  validate → judge → settle        ── atomic; see §11
            │
            ▼
  authoritative response           ── HP, revision, defeat state, next action
            │
            ▼
  render · resume · retry
```

**Retry rule.** A retry re-sends the *same* nonce with the *same* answer. It must never
request a new nonce and never re-derive the answer. A retry that reaches a settled submission
returns the original settled result marked as a duplicate.

**Resume rule.** After reload, an adapter re-reads authoritative battle state from the server.
It must not reconstruct HP from local storage, animation state, or prior responses.

---

## 7. Battle State Machine

**Battle**

```
        create
          │
          ▼
       ┌──────┐  settlement reduces a side to zero   ┌───────────┐
       │ OPEN │ ───────────────────────────────────► │ COMPLETED │
       └──┬───┘                                      └───────────┘
          │ lifecycle expiry
          ▼
      ┌─────────┐
      │ EXPIRED │
      └─────────┘
```

Settlement may only be applied to a battle in `OPEN`. `COMPLETED` is terminal and must carry
a completion timestamp. A battle never returns to `OPEN`.

**Attempt**

```
ISSUED ──► RESERVED ──► SETTLED      (valid answer judged CORRECT or INCORRECT)
   │           └──────► REJECTED     (answer judged INVALID)
   └──► EXPIRED                      (TTL elapsed before submission)
```

**Submission**

```
RESERVED ──► SETTLED      state advanced, damage applied, revision advanced
         └─► REJECTED     no state change, no damage, INVALID recorded
```

An attempt carries **at most one** submission. This is enforced by a database uniqueness
constraint, not by application logic.

**Judge results** are exactly `CORRECT`, `INCORRECT`, `INVALID`. `INVALID` means the
submission could not be judged as a legal answer; it settles no damage and advances no
revision, but is recorded.

---

## 8. Battle Runtime Responsibilities

The Runtime **owns**:

- Request canonicalisation and rejection of client authority fields.
- Feature-mode resolution and eligibility.
- Attempt issuance metadata and expiry enforcement.
- Nonce issuance, hashing, and validation.
- Submission identity (request hash) and duplicate replay.
- Invocation of the versioned judge adapter.
- Damage derivation from the judge result.
- Delegation of settlement to the persistence layer within the caller's transaction.
- The authoritative response shape.

The Runtime **must not**:

- Trust any client-supplied grade, correctness, damage, or HP value.
- Fall back to a non-canonical judge when canonical judging is unavailable.
- Commit or roll back the caller's transaction.
- Emit a raw nonce anywhere other than its single issuance response.
- Branch on which surface is calling.

**Rejected client authority.** Requests carrying any field that would express server authority
— grade, correctness, damage, HP, judge result, reward, zone clear, submission identity, or
settlement timestamps — are rejected outright. Ignoring such fields is insufficient; their
presence indicates a client attempting to settle, and must fail loudly.

---

## 9. Judge Responsibilities

The judge is a **versioned adapter** over the repository's canonical SGF engine. It converts
(authoritative question, issued attempt, canonicalised answer) into
(result, authoritative grade, judge version, reason code).

Contract:

- The judge reads question content from the **authoritative server-side source**. A client
  may identify a question; it may never supply one.
- The judge applies the attempt's recorded board transform. Transform identity is fixed at
  issuance and is not renegotiable at submission.
- Every outcome carries a **reason code** — the audit trail for why a result was reached.
- If canonical judging cannot run, the judge raises *unavailable*. It must never degrade to a
  hand-written parser, heuristic, or client-reported result.
- The judge version is recorded on the attempt at issuance. A submission whose attempt was
  issued under a different judge version is rejected, not re-judged.

Correctness authority belongs to the canonical engine. The Runtime explains and applies;
the engine decides.

---

## 10. Persistence Model

Three owner-scoped tables:

| Table | Owns |
|---|---|
| battles | HP, maxima, zone, lifecycle state, revision counter |
| attempts | question identity, board, colour, transform, judge version, TTL, nonce hash |
| submissions | nonce hash, request hash, canonical answer, result, damage, before/after evidence |

Requirements:

- **Owner scoping is structural.** Every row carries the owning user; every lookup and every
  mutation is scoped by owner and enforced by composite keys and foreign keys. Ownership is
  never checked only in application code.
- **Invariants live in the schema.** HP bounds, permitted states, damage non-negativity,
  result/state coherence, and revision monotonicity are database constraints. Application
  validation is a second line of defence, never the only one.
- **Settlement evidence is durable.** A settled submission records HP before and after,
  revision before and after, result, grade, and timestamps.
- **Schema changes are additive.** New columns and indexes may be added. Existing battle
  columns, states, and constraints are not rewritten in place.
- **The persistence layer never commits.** It executes inside the caller's transaction so a
  failure anywhere in settlement rolls back the whole operation.

Retention is defined for two distinct purposes: idempotency records must outlive any plausible
client retry window, and settled-submission audit evidence is retained substantially longer for
dispute resolution.

---

## 11. Concurrency Model

**This model is frozen. Alternative concurrency designs require a Charter revision.**

```
BEGIN
  ├─ SELECT battle ... FOR UPDATE          serialise concurrent settlement
  ├─ verify battle is OPEN
  ├─ INSERT submission (unique nonce)      exactly-once reservation
  ├─ compare-and-advance revision          optimistic conflict detection
  ├─ apply HP change
  ├─ record settlement evidence
  └─ advance attempt state
COMMIT
```

Each element exists for a distinct failure mode, and none is redundant:

- **Row lock** — serialises two simultaneous settlements against the same battle. Without it,
  both could read the same HP and both write, losing one update.
- **Revision compare-and-advance** — rejects a submission built against state that has since
  changed. The update is conditional on the expected revision *and* on the battle still being
  open; a non-match is a conflict, not a retry-in-place.
- **Unique nonce constraint** — makes exactly-once a property of the database rather than of
  application timing. Under a genuine race, one insert succeeds and the other violates the
  constraint, which is then resolved as a duplicate.
- **Single transaction** — guarantees there is no observable intermediate state in which
  damage is applied but evidence is missing, or vice versa.

Conflicts surface as explicit, stable error codes. They are never silently retried by the
server, and never resolved by re-judging.

Note on portability: the production database is PostgreSQL and the locking semantics above are
PostgreSQL semantics. Any lighter-weight database path that exists for deterministic testing
must not be presented, documented, or relied upon as a concurrency equivalent.

---

## 12. Idempotency

Two identifiers, with different jobs:

- **Submission nonce** — server-issued, bound to owner + battle + attempt. Answers the
  question *"is this the same submission?"*
- **Request hash** — derived from the canonicalised answer. Answers the question *"is this the
  same answer?"*

Rules:

1. Same nonce, same request hash, already settled → **replay** the stored result, marked as a
   duplicate. Do not re-judge. Do not re-apply damage.
2. Same nonce, **different** request hash → reject as conflict. The nonce is a submission
   identity, not a reusable credential.
3. Nonce absent, unissued, expired, forged, or belonging to another attempt or another owner →
   reject. No settlement.

The request hash deliberately excludes optimistic-concurrency metadata such as the battle
revision. A transport retry may legitimately carry a revision observed from an earlier
response; that retry is still the *same answer* and must replay rather than conflict. Answer
identity and concurrency metadata are separate concerns and must remain separately represented.

---

## 13. Security Model

**Threat model.** The client is untrusted. Assume an adversary who fully controls the browser,
can replay and reorder requests, and can read any value the server has ever sent them.

Controls:

- **Server authority.** Outcome-bearing fields are rejected on input (§8).
- **Ownership.** Every battle, attempt, and submission is owner-scoped structurally. Cross-account
  access fails at the query boundary.
- **Nonce secrecy.** Nonces are generated from a cryptographically suitable random source. Only
  the hash is stored. The raw value is returned exactly once at issuance and must never appear
  in a log, an error message, an evidence artefact, a replayed response, or a SQL statement.
- **Constant-time comparison.** Nonce and request-hash comparisons use constant-time equality.
- **Question integrity.** Question identity and revision are fixed at issuance. A stale or
  substituted question revision is rejected rather than judged.
- **Attempt expiry.** Attempts carry a server-set TTL. Expired attempts cannot settle.
- **Fail-closed feature gating.** An unrecognised feature-mode value resolves to *off*.
- **Protocol versioning.** Clients too old to satisfy the contract receive an explicit
  upgrade-required response rather than a degraded path.

**Prohibited under all conditions**, including error, timeout, feature-off, judge-unavailable,
and adapter-initialisation failure: routing battle damage through the spaced-repetition review
endpoint, or through any other endpoint that does not implement this Charter. There is no
fallback damage path. A battle that cannot be settled correctly is not settled at all.

---

## 14. Adapter Responsibilities

An adapter is a **thin, surface-specific translator**. It owns:

- Collecting battle context from its surface (zone, encounter, question identity).
- Calling the Runtime's endpoints.
- Retaining issued identity — battle id, attempt id, nonce, revision — for retry.
- Applying the authoritative response to its surface's view state.
- Presenting Runtime error codes as surface-appropriate messages.

An adapter **must not**:

- Compute or adjust grade, damage, or HP.
- Request a new nonce in order to retry.
- Infer battle outcome from animation, timing, or local state.
- Reach any settlement path other than the Runtime's.
- Introduce a second copy of game-balance rules.

All adapters must resolve to the **same** runtime service, the same endpoints, the same damage
derivation, and the same settlement path. Adapters may share presentation components freely;
runtime identity must be singular. An adapter that reports a different runtime service
identity than the one it expects must treat that as a hard failure.

---

## 15. Frontend Responsibilities

The frontend renders authoritative state. It is not a participant in settlement.

- HP shown to the player is HP the server most recently reported.
- Animation is presentation. A failed, skipped, or interrupted animation must never change HP,
  and HP must never be derived from animation completion.
- Optimistic UI is permitted only as a *visual* affordance and must reconcile to the
  authoritative response. It must never be committed as state.
- After reload, resume by re-reading server state.

Every adapter surface must handle, at minimum: issuance pending, submission pending, duplicate
response, nonce conflict, stale revision, expired attempt, feature unavailable, upgrade
required, server error, monster defeat, and player defeat.

---

## 16. Packaging Contract

The Runtime is only correct in production if it is actually *shipped*. Packaging is therefore
part of this contract, not an operational afterthought.

- Every runtime module the application imports must be present in the build manifest.
- Every asset referenced by served HTML must be present in the governed asset closure.
- Client runtime files must carry cache identity consistent with the release; a stale cached
  adapter is a client that no longer satisfies this Charter.
- Packaging verification fails closed. A missing governed file is a failed release, never a
  partial one.

A Runtime change that is correct in the repository and absent from the image is a production
defect of the same severity as an incorrect settlement.

---

## 17. Testing Strategy

Required coverage, by category:

**Lifecycle** — battle creation; resume; attempt issuance; nonce issuance; settlement of
correct, incorrect, and invalid answers; attempt expiry; battle completion on either defeat.

**Idempotency** — duplicate retry replays the settled result; same nonce with a different
answer is rejected; retry carrying an updated revision still replays; concurrent submission of
the same nonce yields exactly one settlement.

**Concurrency** — competing settlements against one battle serialise; stale revision is
rejected; a failure mid-settlement leaves no partial state.

**Security** — forged grade, correctness, damage, and HP fields; cross-account battle, attempt,
and nonce access; question substitution; stale question revision; colour and transform
spoofing; replay; nonce forgery; missing nonce.

**Isolation** — battle damage must be proven not to reach the spaced-repetition review endpoint
under any condition, including every failure path. This must be verified by observing actual
network calls. Source-text search is not acceptable evidence.

**Boundary** — the Runtime's import set must be asserted to contain no adapter, surface, or
web-framework module. This is a test, not a review convention.

Determinism requirement: tests must not depend on wall-clock timing for correctness. Time-dependent
behaviour is exercised by injecting the timestamp.

---

## 18. Rollout Strategy

The Runtime ships behind a server-controlled feature mode that supports, in increasing order of
exposure: off, validation-only, administrator, allowlist, percentage, and global.

- **Default is off.** An unset or unrecognised value resolves to off.
- **Validation-only** mode exercises the full request and judging path and returns a result
  without settling any state. It is the correct way to observe real traffic before exposure.
- Exposure widens one step at a time. Each step is a deliberate decision, not a schedule.
- The mode is server-side configuration. It is never client-selectable and never inferred from
  a request.

Schema must be deployed and verified before any mode above *off* is enabled.

---

## 19. Rollback Strategy

- **Feature mode is the first-line rollback.** Returning the mode to off stops all new
  settlement immediately without a deploy.
- **Persisted battles survive rollback.** Because state is server-side and additive, disabling
  the feature does not corrupt or orphan existing battles.
- **No destructive rollback of settled evidence.** Settled submissions are audit records.
  Rolling back a release must not delete them.
- **Code rollback follows the repository's deployment governance** (ADR-0001), including its
  ownership gates. Rolling the application back to a build that predates a schema addition must
  be verified as safe against the additive-only property before it is attempted.
- A failed post-deploy acceptance is resolved by rollback, not by hotfixing production.

---

## 20. Operational Guidance

**Diagnosing a disputed battle outcome.** Every settlement is reconstructible from the
submission record: the canonical answer, the result, the reason code, the judge version, HP
before and after, and the revision it advanced. Start there, not from client logs.

**Interpreting conflicts.** A conflict result is usually correct behaviour, not a defect — it
indicates two writers, a stale client, or a retry against changed state. Investigate frequency,
not individual occurrences.

**Interpreting duplicates.** A duplicate response means idempotency worked. A rising duplicate
rate indicates network conditions or client retry behaviour, not a Runtime fault.

**Judge-unavailable is a hard signal.** It means canonical judging could not run. It must never
be silenced by introducing a fallback path. Treat sustained occurrence as a production incident.

**Never repair battle state by direct database mutation.** A battle whose state is wrong is
evidence. Correct the defect, then decide the player-facing remedy deliberately.

---

## 21. Engineering Invariants

These are permanent. Each states a rule, why it exists, and what breaks without it. Violating
any of them is a correctness defect, not a style disagreement. Adding to this list is a Charter
revision; removing from it is a Charter revision with explicit justification.

**I-1. Battle truth belongs to the server.**
*Rationale:* The client is fully controllable by the player. If any part of battle truth
originates client-side, then battle outcomes are advisory and every downstream reward, ranking,
and progression signal built on them is unreliable.

**I-2. The client never settles HP.**
*Rationale:* HP is shared, persisted, cross-session state. A client that writes it creates
states no server can arbitrate — two tabs disagreeing, a reload resurrecting a defeated
monster, a refresh erasing progress the player earned.

**I-3. The client never computes authoritative damage.**
*Rationale:* Damage is game balance. A second implementation in the browser guarantees eventual
divergence from the server's rules, and the divergence is invisible until players notice the
inconsistency.

**I-4. The Runtime never imports adapters.**
*Rationale:* The moment the core knows about a surface, every new surface requires core changes,
and every core change risks every existing surface. One-way dependency is what makes additional
battle surfaces cheap and safe.

**I-5. Adapters depend on the Runtime, never the reverse.**
*Rationale:* Two surfaces integrating "their own way" produces two settlement paths, which
produces two sets of bugs and two definitions of correctness. A single direction of dependency
is what keeps one definition.

**I-6. Battle damage never routes through the spaced-repetition review endpoint.**
*Rationale:* That endpoint exists to record study progress. It has no battle state, no ownership
model for battles, and no ability to reject an implausible outcome. This was the original defect;
re-introducing it as a fallback would restore exactly the failure this Runtime was built to end.

**I-7. There is no fallback settlement path.**
*Rationale:* A fallback is used precisely when the primary path is failing — which is when
correctness matters most and is least verifiable. Failing closed produces a visible, fixable
error; falling back produces silent, permanent state corruption.

**I-8. A duplicate retry never replays settlement effects.**
*Rationale:* Mobile networks retransmit routinely. Without exactly-once settlement, ordinary
connectivity loss silently double-applies damage, and players lose or win battles based on
network conditions rather than skill.

**I-9. The submission nonce is server-issued and authoritative.**
*Rationale:* If the client can choose the identifier, it can choose to make two different
answers look identical, or one answer look like two. Submission identity must originate from
the party that has something to protect.

**I-10. Only the nonce hash is stored; the raw nonce is returned exactly once.**
*Rationale:* A stored raw nonce turns any database read, log capture, or leaked backup into a
replay capability. Storing only the hash means a leak of data at rest does not grant the ability
to forge a submission.

**I-11. Settlement is atomic.**
*Rationale:* Partial settlement — damage applied without evidence, or evidence without a revision
advance — produces battle state that cannot be audited or safely resumed. There must be no
observable intermediate state.

**I-12. Replay protection is mandatory, not optional per surface.**
*Rationale:* A single surface that omits it reopens the vulnerability for the whole system, and
the omission will not be visible until it is exploited or until a player's battle silently breaks.

**I-13. Given identical inputs and server-issued seed, settlement is deterministic.**
*Rationale:* Non-determinism makes a disputed outcome unreconstructible and makes regression
testing impossible. Future battle types may legitimately introduce randomness — boss behaviour,
loot — but the random source must be a server-issued seed recorded with the battle, so that any
settlement remains reproducible from stored evidence. Determinism is required at the settlement
layer specifically; it does not forbid randomness, it forbids *unrecorded* randomness.

**I-14. Ownership is enforced structurally, not only in application code.**
*Rationale:* Application-level checks are one forgotten line away from a cross-account defect.
Composite keys and foreign keys make the wrong query impossible rather than merely incorrect.

**I-15. Schema evolution is additive.**
*Rationale:* Battles are long-lived and may be in progress across a deploy. Rewriting existing
columns or constraints risks invalidating live battles and forecloses rollback.

**I-16. Packaging must include every runtime module and every asset referenced by served HTML.**
*Rationale:* A Runtime that is correct in the repository and missing from the image fails in
production in ways that look like unrelated client bugs, and costs disproportionate time to
diagnose.

**I-17. Feature flags default fail-closed.**
*Rationale:* An unrecognised or unset configuration value must never mean "enabled." A
misconfiguration should reduce exposure, never silently widen it.

**I-18. Canonical judging is the sole correctness authority.**
*Rationale:* A second judging implementation — however small, however well-intended — becomes a
second definition of "correct answer," and the two will diverge. The Runtime explains and
applies; the canonical engine decides.

---

## 22. Future Extensions

Anticipated additions, and what each is expected to require:

| Extension | Expected shape |
|---|---|
| Additional map surfaces | New adapter only. No Runtime change. |
| Guild / cooperative battles | Runtime change: multi-participant ownership and settlement ordering. Requires Charter revision. |
| Boss and raid battles | Runtime change: server-issued seed, recorded with the battle (see I-13). Requires Charter revision. |
| Alternate judging rules | New judge version. Existing attempts remain bound to the version they were issued under. |
| Rewards and progression | Downstream consumer of settled submissions. Must read settlement evidence; must not re-derive outcomes. |

Extensions that require a Runtime change must state so explicitly and revise this Charter before
implementation. An extension implemented by special-casing a surface inside the Runtime violates
I-4 regardless of how small the special case is.

---

## 23. Document Governance

This Charter is a long-term engineering contract. It is not a sprint document, a release note, a
design draft, or a historical record.

- If Battle Runtime architecture changes, **the Charter changes with it.** Changing the code
  alone is not a complete change.
- Compatible clarifications and additions: revise in place and increment the Charter Version,
  updating the Date.
- A change that invalidates a stated invariant or the frozen concurrency model requires a **new
  Charter version**; the prior version's Status becomes `Superseded` and the new version records
  what it supersedes.
- Silent divergence between code, architecture, and this document is itself a defect.
- This Charter is the single authoritative source for Battle Runtime engineering rules.
  Parallel or duplicate versions must not be created.

Related governance, which this Charter does not restate and does not override:

- `docs/architecture/ADR-0001-canonical-repository-and-deployment.md` — canonical repository,
  branch, and deployment governance, including ownership gates.
- `docs/project-os-v2.md` — risk classes, sprint lifecycle, and production gates.

---

## 24. Future Task Contract

Any task that touches the Battle Runtime, its adapters, its schema, or its packaging must load
this Charter before beginning work, and must report that it did so.

```
Architecture Baseline
Read:
GO_ODYSSEY_BATTLE_RUNTIME_PROJECT_CHARTER.md
Return:
PROJECT_CHARTER_LOADED
Version: <Charter Version from the Metadata Block>
Sections Loaded: <sections relevant to the task>
Proceed only after Charter loading.
```

The reported Version is the `Charter Version` value in the Metadata Block at the top of this
document.

A task that discovers a conflict between this Charter and the implementation must **stop and
report the conflict**. It must not resolve the conflict by quietly following the code, and it
must not weaken a stated invariant in order to proceed.

---

## 25. Glossary

**Adapter** — Surface-specific translator between a battle surface and the Runtime. Owns
transport and context; owns no authority.

**Attempt** — A server-issued opportunity to answer one question within one battle. Fixes
question identity, revision, board size, player colour, transform, judge version, and expiry.

**Authoritative grade** — The server's quality rating of a correct answer, used to derive damage.

**Battle** — A persisted, owner-scoped encounter holding player and monster HP, lifecycle state,
and a revision counter.

**Battle revision** — Monotonically increasing counter used for optimistic concurrency. Advances
exactly once per settlement.

**Canonical judging** — Evaluation against authoritative question content by the repository's SGF
engine. The sole correctness authority.

**Duplicate** — A submission recognised as already settled, whose stored result is replayed
rather than recomputed.

**Fail-closed** — Resolving ambiguity toward no action and no exposure.

**Feature mode** — Server-side setting controlling Runtime exposure. Defaults to off.

**Idempotency** — The property that repeated delivery of one logical submission produces exactly
one settlement.

**Judge version** — Identifier of the judging contract an attempt was issued under. Attempts do
not migrate between judge versions.

**Reason code** — Short, stable explanation of why a judge reached its result. Audit evidence.

**Request hash** — Hash of the canonicalised answer, identifying *which answer* was submitted.
Excludes concurrency metadata.

**Settlement** — The atomic transaction that judges a submission, applies damage, advances the
revision, records evidence, and transitions attempt state.

**Submission** — One recorded answer against one attempt. At most one per attempt.

**Submission nonce** — Server-issued single-use token identifying one submission. Returned once;
stored only as a hash.

**Surface** — A place in the product where battles occur (Legacy Adventure, E10 World Map, and
future battle contexts).
