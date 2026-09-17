# P0 duplicate/replay acceptance boundary

`DUPLICATE_REPLAY_DELTA=NOT_VERIFIED`.

No safe, already-authorized acceptance path was available that could replay
the exact Production contribution without submitting another request as the
real `test01` account or mutating a player record. No arbitrary player was
used, and no toolbar mutation or answer replay was clicked.

The existing bounded contracts continue to prove the protection path:

- Lane B browser contract: PASS
- Map Battle/provider runtime: 16 passed
- existing duplicate/idempotency guards remain covered by the Lane B and
  Map Battle tests

This is not a claim that a live duplicate delta is zero. The original forward
incident remains open until a separately approved safe acceptance records
`DUPLICATE_REPLAY_DELTA=0` and an exact UTC closure timestamp.

`DUPLICATE_REPLAY_STATUS=SEPARATE_SAFE_ACCEPTANCE_REQUIRED`
