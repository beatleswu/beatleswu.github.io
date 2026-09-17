# P0 real non-admin Adventure +1 evidence

## Owner-provided acceptance preserved

- Account: `test01`
- `NONADMIN=YES`
- `OWNER_TEST_ZONE=k26_30`
- `PROGRESS_BEFORE=59`
- `PROGRESS_AFTER=60`
- `PROGRESS_DELTA=1`
- `REAL_NONADMIN_ADVENTURE_PROGRESS_PLUS_ONE=PASS`

## Fresh read-only Production corroboration

- `users`: `(991111, test01, is_admin=0)`
- current `map_battles` row for that user: zone `k26_30`, battle id
  `b5aa8a7346e04774b68b7e5b5e46142d`, state `OPEN`
- latest read-only settlement: submission
  `76c923c0b1284386b4d2791eded295b4`, source context
  `mbv1:76c923c0b1284386b4d2791eded295b4`, question `31192`, grade `5`,
  reviewed at `2026-09-17T00:34:22.244643`
- the latest four `mbv1` review rows for this account are server-owned
  `CORRECT` Map Battle settlements; no client grade was used as authority.

The read-only corroboration did not submit, replay, or alter `test01` state.
The exact UI counter transition remains the Owner's recorded `59 -> 60`
acceptance evidence.
