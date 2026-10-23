# G076 R3-C Daily coordinator integration (NOT APPLIED)

Base: `0b358cc7e5987ffc335dd1b7088b4299b1585518`, branch
`g076-r3c-daily-codex`. This lane intentionally does not edit app.py, index.html,
Dockerfile, deploy/build-manifest.json, or shared step modules. Local Daily work
is reviewable, but application wiring, schema admission, packaging, release and
Owner acceptance remain HOLD. No push / PR / merge / deploy is authorized here.

## Surgical app.py instructions

Apply these additions only in the coordinator's authorized lane. Keep existing
login decorators, global request policies and asset path validation. Do not
register the shared nonmap blueprint a second time or replace Practice routes.

1. Add imports:

```python
from g076_daily_step_integration import (
    DailyServices, create_daily_blueprint, select_daily_question,
    enabled as g076_daily_steps_enabled,
)
```

2. After `dc_submit`, `check_and_award_daily`, `give_daily_appearance`,
`get_daily_submit_streak`, `_map_battle_question_context`, `BADGE_DEFS` and
`_APPEAR_MAP` exist, before the application starts serving, add:

```python
@contextmanager
def _g076_daily_transaction():
    conn = get_db()
    try:
        raw = getattr(conn, '_conn', conn)
        sqlite = raw.__class__.__module__.startswith('sqlite3')
        conn.execute('BEGIN IMMEDIATE' if sqlite else 'BEGIN')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _g076_daily_question(conn, day):
    return select_daily_question(conn, day, load_questions=_load_questions)


def _g076_daily_admit(uid, question):
    # Daily currently admits authenticated users, independent of Practice's
    # premium/rank/quota policy. Blueprint checks authenticated session on EACH
    # request. Do not replace this with Practice's free-question quota debit.
    # Preserve any coordinator-added account suspension / Daily policy here.
    if type(uid) is not int or uid < 1:
        raise NonMapRejected('authentication_required', 401)


_g076_daily_services = DailyServices(
    DAILY_CHALLENGE_XP_REWARD=DAILY_CHALLENGE_XP_REWARD,
    xp_to_lv=xp_to_lv, lv_progress=lv_progress,
    check_and_award_daily=check_and_award_daily,
    get_daily_submit_streak=get_daily_submit_streak,
    give_daily_appearance=give_daily_appearance,
    BADGE_DEFS=BADGE_DEFS, _i18n_badge_en=_i18n_badge_en,
    _APPEAR_MAP=_APPEAR_MAP,
)
app.register_blueprint(create_daily_blueprint(
    transaction=_g076_daily_transaction,
    today_question=_g076_daily_question, admit=_g076_daily_admit,
    services=_g076_daily_services, secret=app.secret_key, environ=os.environ,
    question_context=_map_battle_question_context,
))
```

Import `NonMapRejected` from `g076_nonmap_steps` for this snippet. Both transaction
and all three effect providers MUST retain the same connection, propagate errors,
and never commit or open another transaction. The existing providers meet that
contract at the base revision. Do not use the legacy `get_or_create_daily_challenge`
inside this transaction: it opens and commits its own connection.

3. In `dc_submit`, immediately AFTER its existing:

```python
    if replay is not None:
        return jsonify(replay)
```

insert:

```python
    if g076_daily_steps_enabled(os.environ):
        return jsonify({'ok': False, 'error': 'daily_steps_required'}), 409
```

This retains historical exact D5B response-loss replays before the new-attempt
gate. New legacy submissions cannot bypass steps while Daily is enabled. The
existing unique `(user_id, challenge_date)` insert remains REQUIRED even with this
gate: feature changes and requests already in flight can race. Both paths insert
that same row BEFORE any XP/badge/appearance effect. The losing path rolls back
its D5B reservation. Tests race the UNMODIFIED legacy route against the adapter,
which proves this stronger fallback without depending on the added gate.

4. In `dc_today`, immediately after `uid = session['user_id']`, insert:

```python
    if g076_daily_steps_enabled(os.environ):
        return app.view_functions['g076_daily_steps.today']()
```

This gives any old Daily consumer the same board-only response and synchronizer
CSRF token. Do not expose raw SGF through this alias or history detail. Global
privacy enforcement remains a prerequisite; this lane does not certify all
other answer-bearing endpoints or consumers.

5. Add the two exact asset routes, following the existing
`g076_authoritative_step_client.js` route's safe asset helper convention:

```python
@app.route('/js/game/g076_nonmap_step_client.js')
def g076_nonmap_step_client_asset():
    return _serve_live_static_or_baked_subpath(
        'g076_nonmap_step_client.js', 'js/game', 'js/game'
    )

@app.route('/js/game/g076_daily_step_client.js')
def g076_daily_step_client_asset():
    return _serve_live_static_or_baked_subpath(
        'g076_daily_step_client.js', 'js/game', 'js/game'
    )
```

At the base revision the helper is `_serve_live_static_or_baked_subpath`. Preserve
the coordinator's current safe helper contract; do not create a broad static
file route. Also ensure `/wgo/wgo.player.min.js` is served (the board-only SGF
parser uses its existing WGo parser). Avoid duplicate asset registrations if
another lane already registered the shared client.

## Admission and remaining gates

All three flags must be explicitly enabled for any Daily endpoint:
`G076_ANSWER_PRIVACY_ENFORCED`, `G076_NONMAP_STEPS_ENABLED`,
`G076_DAILY_STEPS_ENABLED`. Defaults are OFF, with HTTP 503 and no legacy UI
fallback. This source does not set any environment variable. Flag OFF intentionally
leaves the new standalone page unavailable until coordinator wiring/admission.

Before enabling, admit the existing proposed `g076_nonmap_steps_PROPOSED.sql`
with the required primary/foreign keys, existing D5B review identity migration,
and unique `daily_challenge_log(user_id,challenge_date)`. Runtime never creates
schema. Missing tables/columns fail preflight; missing conflict-target uniqueness
fails before credit. Production schema qualification is NOT_EXECUTED here.

Selection preserves the existing MD5 date-seeded algorithm, rereads the unique
date winner, respects admin selection and fails for duplicate/missing question
identities. It does not silently select another question when preflight fails.
Preflight walks EVERY solution branch and rejects unsupported answer alternatives,
pass replies, ambiguous opponent replies, invalid or excessive trees. The shared
step and final Daily judges must agree before settlement.

`settle_daily` rechecks uid/date/question/revision/content binding, uses the
canonical final judge, reserves D5B, wins the daily row, performs original XP,
badge/streak/appearance writes and persists the original D5B result envelope on
ONE connection. The terminal step event commits in that same transaction. The
client only receives the shared allowlisted receipt and played opponent move.
It cannot propose uid/date/grade/history/correctness/settlement identity.

The base `dc_submit` has NO quota debit, refund, explicit quest-runtime event,
SRS, or wallet reward. Therefore none is invented here. Its D5B review row remains
present once for existing review-log consumers. Exact future quest-runtime event
admission is HOLD until an authoritative Daily contract is supplied; this lane
makes no claim that an unobserved quest award occurred. XP shadow and shadow judge
are post-commit advisory observers in the old route, omitted from the atomic
adapter and not replaced with a new durable award source.

The page hides answer/abandon/manual-submit controls because no authoritative
abandon/reveal endpoint exists. Wrong is final for the date; retry recovers the
same uncertain move, never resets the attempt. Reload resumes server history or
shows the committed date result. The result panel displays server verdict/XP;
new badge/appearance metadata remains in the D5B result, not the step response.
Historical board review needs a safe board-only response, and does not award XP.
No complete R3, Production readiness, or deployment claim follows from Daily.
