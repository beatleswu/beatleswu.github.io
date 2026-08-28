# F028 `app.py` thin-wiring proposal

Status: **prepared, not applied**

This proposal is the exact writer handoff for
`F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_ACQUISITION_CLOSURE_001`.
It is based on `c2a1dab3125cdef0cff381815d3d995bdd340538` plus the accepted but
not master-merged F027-R1 dependency
`a16cb7f7d8c17680bbb00d02d548a027e89ac0cf`.

`app.py` remains untouched because its current single writer is
`B050_PUBLIC_SRS_REVIEW_SERVER_AUTHORITY_CLOSURE_001`.

## Existing authority being preserved

The current `/api/adventure/boss/finish` route already:

1. authenticates through `@login_required`;
2. recomputes the score from server-side `review_log` evidence;
3. calls `_adventure_boss_record_attempt()`;
4. uses `adventure_boss_progress(user_id, zone_key).cleared` and the
   conditional `cleared=0` transition to identify `is_first_clear`; and
5. owns the progress transaction through `with get_db() as conn`.

The proposal adds no second first-clear table, no client reward input, no
world-progression mutation, and no `player_appearance` write.

## Exact thin patch

Add the following import to the existing application import block (for
example immediately after the existing presentation/equipment service
imports):

```diff
@@
 from equipment_ownership_service import (
     EquipmentOwnershipError,
     grant_equipment_ownership,
 )
+from battlefield_boss_reward_service import (
+    BattlefieldBossFirstClearSettlement,
+    BattlefieldBossRewardError,
+    grant_battlefield_boss_first_clear_reward,
+)
```

In `adventure_boss_finish`, replace the current first-clear coin-only block:

```diff
@@
         settlement = _adventure_boss_record_attempt(
             conn, uid, zone_key, passed, correct, cooldown_until, now,
         )
         is_replay = settlement['is_replay']
         is_first_clear = settlement['is_first_clear']

-        # Same transaction as the clear-progress upsert above: if the reward
-        # grant fails, the whole `with` block rolls back (db.py commits on
-        # clean exit, rolls back on exception) -- a boss clear can never be
-        # recorded without its first-clear reward, or vice versa.
-        reward_coins = 0
-        if is_first_clear:
-            reward_coins = _grant_coins(
-                conn, uid, ADVENTURE_FIRST_CLEAR_REWARD_COINS,
-                f'adventure_first_clear:{zone_key}', bypass_daily_cap=True,
-            )
+        # The attempt result is the only first-clear authority.  The F028
+        # service writes the existing wardrobe authority in this same caller
+        # transaction and never accepts a request-body reward id.
+        try:
+            boss_settlement = BattlefieldBossFirstClearSettlement.from_authoritative_attempt(
+                user_id=uid,
+                zone_key=zone_key,
+                passed=passed,
+                attempt_result=settlement,
+            )
+            reward_result = grant_battlefield_boss_first_clear_reward(
+                conn,
+                boss_settlement,
+                appearance_definitions=APPEARANCE_DEFS,
+                presentation_registry=PURE_COSMETIC_PRESENTATION_REGISTRY,
+                appearance_effects=APPEARANCE_EFFECTS,
+                obtained_at=now,
+            )
+        except BattlefieldBossRewardError as exc:
+            # The progress transition must not commit when reward identity or
+            # catalog authority is unavailable.  Leave the exam in session so
+            # a corrected retry can be attempted; do not report success.
+            conn.rollback()
+            return jsonify({'ok': False, 'error': exc.code}), 400
```

Replace the response reward fields with the server-authored F028 projection:

```diff
@@
         'attempt_mode': 'replay' if is_replay else 'first_clear',
         'replay': is_replay,
-        'reward': {'coins': reward_coins, 'first_clear': is_first_clear},
+        'reward': {
+            # Preserve the existing response key without granting a currency
+            # fallback or already-owned compensation.
+            'coins': 0,
+            **reward_result.as_response(),
+        },
+        'reward_item': reward_result.as_response()['reward_item'],
         **map_state,
     })
```

The unused `ADVENTURE_FIRST_CLEAR_REWARD_COINS` constant and its explanatory
comment can then be removed in the same `app.py` writer change.  No other
coin call is part of this proposal.  A failed Boss, replay, or already-owned
first-clear path must return `coins: 0` and no replacement reward.

## Required writer-side verification

The B050 writer should update the existing Boss route regression expectations
and add route-level cases that use the accepted F028 service:

- all ten persisted `ADVENTURE_ZONES` keys resolve to the locked Mapping A
  identity;
- a passed first-clear transition inserts one `player_wardrobe` row;
- a replay does not insert a second row;
- an already-owned first-clear consumes the clear entitlement without coins;
- an ownership-write exception rolls the progress transition back;
- request-body `reward_id` is ignored/rejected and never selects content;
- `player_appearance` remains unchanged; and
- the response contains only server-authored reward identity and the F027
  presentation contract.

The current F028 branch tests the service and this proposal without applying
the route.  Until this thin patch is separately applied and reviewed,
F028's live route closure is intentionally **pending app.py writer wiring**.
