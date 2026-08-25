"""F006 Monster settlement, lineage, and roster-cardinality tests."""

from dataclasses import replace
import sqlite3

import pytest

from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from monster_drop_profiles import CANONICAL_DROP_PROFILE_REGISTRY
from monster_identity import CANONICAL_MONSTER_IDENTITY_REGISTRY
from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    MonsterProfileRegistry,
)
from monster_reward_profiles import CANONICAL_REWARD_PROFILE_REGISTRY
from monster_settlement import (
    MonsterSettlementRejected,
    build_monster_defeated_event,
    next_roster_entry,
    settle_monster_defeat,
)


class FixedRandom:
    def __init__(self, value=0.0):
        self.value = value
        self.random_calls = 0
        self.choice_calls = 0

    def random(self):
        self.random_calls += 1
        return self.value

    def choices(self, entries, *, weights, k):
        self.choice_calls += 1
        assert k == 1
        return [entries[0]]


def _db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    upgrade_outbox(conn)
    conn.executescript(
        """
        CREATE TABLE player_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL
        );
        CREATE TABLE player_wardrobe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE(user_id, item_id)
        );
        CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE currency_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            reason TEXT NOT NULL
        );
        """
    )
    return conn


def _synthetic_registry():
    """Add one test-only profile through the same canonical interfaces."""

    base = CANONICAL_MONSTER_PROFILE_REGISTRY.by_id['legacy_bf_07_normal']
    extra = replace(
        base,
        monster_id='synthetic_extra_monster',
        roster_slot=21,
        zone_key='zone_11_test_only',
        display_key='monster.test.synthetic_extra',
        legacy_aliases=('synthetic_extra_monster',),
    )
    profiles = tuple((*CANONICAL_MONSTER_PROFILE_REGISTRY.profiles, extra))
    return MonsterProfileRegistry(
        profiles=profiles,
        by_id={profile.monster_id: profile for profile in profiles},
        by_roster_slot={profile.roster_slot: profile for profile in profiles},
        stat_profiles=CANONICAL_MONSTER_PROFILE_REGISTRY.stat_profiles,
        drop_profiles=CANONICAL_MONSTER_PROFILE_REGISTRY.drop_profiles,
        reward_profiles=CANONICAL_MONSTER_PROFILE_REGISTRY.reward_profiles,
        presentation_profiles=CANONICAL_MONSTER_PROFILE_REGISTRY.presentation_profiles,
    )


def _grant_callbacks(conn):
    def grant_coins(amount, reason):
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(1)')
        conn.execute('UPDATE user_stats SET coins=coins+? WHERE user_id=1', (amount,))
        conn.execute(
            'INSERT INTO currency_log(user_id,delta,reason) VALUES(1,?,?)',
            (amount, reason),
        )
        return amount

    def grant_functional(item_id, quantity, source):
        for _ in range(quantity):
            conn.execute(
                'INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) '
                'VALUES(1,?,0,?,?)',
                (item_id, 'now', source),
            )
        row = conn.execute(
            'SELECT id FROM player_inventory ORDER BY id DESC LIMIT 1'
        ).fetchone()
        return {'grant_id': f'player_inventory:{row[0]}', 'payload': {'item_id': item_id}}

    def grant_wardrobe(item_id, source):
        conn.execute(
            'INSERT OR IGNORE INTO player_wardrobe(user_id,item_id,obtained_at,source) '
            'VALUES(1,?,?,?)',
            (item_id, 'now', source),
        )
        row = conn.execute(
            'SELECT id FROM player_wardrobe WHERE user_id=1 AND item_id=?',
            (item_id,),
        ).fetchone()
        return {
            'new': row is not None,
            'grant_id': f'player_wardrobe:{row[0]}' if row else '',
            'payload': {'item_id': item_id},
        }

    return grant_coins, grant_functional, grant_wardrobe


def _event(*, settlement_id='settlement-1', monster_id='synthetic_extra_monster'):
    return build_monster_defeated_event(
        settlement_id=settlement_id,
        user_id=1,
        monster_id=monster_id,
        zone_id='zone_11_test_only',
        roster_slot=21,
        encounter_class='NORMAL',
        family_id='fox',
        hp_before=100,
        hp_after=0,
    )


def test_defeat_transition_requires_server_hp_boundary():
    with pytest.raises(MonsterSettlementRejected):
        build_monster_defeated_event(
            settlement_id='bad', user_id=1, monster_id='legacy_bf_01_normal',
            hp_before=0, hp_after=0,
        )
    with pytest.raises(MonsterSettlementRejected):
        build_monster_defeated_event(
            settlement_id='bad', user_id=1, monster_id='legacy_bf_01_normal',
            hp_before=100, hp_after=1,
        )


def test_one_defeat_grants_once_and_retry_replays_without_reroll():
    conn = _db()
    rng = FixedRandom(0.0)
    callbacks = _grant_callbacks(conn)
    kwargs = dict(
        monster_registry=_synthetic_registry(),
        drop_registry=CANONICAL_DROP_PROFILE_REGISTRY,
        reward_registry=CANONICAL_REWARD_PROFILE_REGISTRY,
        random_source=rng,
        grant_coins=callbacks[0],
        grant_functional_item=callbacks[1],
        grant_wardrobe_item=callbacks[2],
    )
    first = settle_monster_defeat(conn, _event(), **kwargs)
    conn.commit()
    assert first.duplicate is False
    assert first.functional_drop_id == 'iron_sword'
    assert first.functional_lineage_count == 1
    assert first.quest_event['event_type'] == 'MONSTER_DEFEATED'

    retry_rng = FixedRandom(0.0)
    second = settle_monster_defeat(
        conn,
        _event(),
        **{**kwargs, 'random_source': retry_rng},
    )
    assert second.duplicate is True
    assert retry_rng.random_calls == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='MONSTER_DEFEATED'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'"
    ).fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM player_inventory').fetchone()[0] == 1
    assert conn.execute('SELECT coins FROM user_stats WHERE user_id=1').fetchone()[0] == 2


def test_no_drop_is_replayed_without_second_roll():
    conn = _db()
    callbacks = _grant_callbacks(conn)
    rng = FixedRandom(1.0)
    kwargs = dict(
        monster_registry=_synthetic_registry(),
        drop_registry=CANONICAL_DROP_PROFILE_REGISTRY,
        reward_registry=CANONICAL_REWARD_PROFILE_REGISTRY,
        random_source=rng,
        grant_coins=callbacks[0],
        grant_functional_item=callbacks[1],
        grant_wardrobe_item=callbacks[2],
    )
    first = settle_monster_defeat(
        conn, _event(settlement_id='no-drop'), **kwargs
    )
    conn.commit()
    assert first.functional_drop_id is None
    retry_rng = FixedRandom(0.0)
    second = settle_monster_defeat(
        conn, _event(settlement_id='no-drop'), **{**kwargs, 'random_source': retry_rng}
    )
    assert second.duplicate is True
    assert retry_rng.random_calls == 0
    assert conn.execute('SELECT COUNT(*) FROM player_inventory').fetchone()[0] == 0


def test_unknown_profile_fails_closed():
    conn = _db()
    with pytest.raises(MonsterSettlementRejected):
        settle_monster_defeat(
            conn,
            _event(monster_id='not-in-canonical-registry'),
            monster_registry=CANONICAL_MONSTER_PROFILE_REGISTRY,
        )


def test_synthetic_extra_monster_uses_generic_roster_selection():
    roster = tuple((f'monster-{index}', index) for index in range(21))
    index, entry = next_roster_entry(roster, 19)
    assert index == 20
    assert entry == ('monster-20', 20)
    index, entry = next_roster_entry(roster, 20)
    assert index == 0
    assert entry == ('monster-0', 0)


def test_d5a_event_types_accept_monster_defeat_without_schema_change():
    conn = _db()
    row = conn.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='MONSTER_DEFEATED'"
    ).fetchone()
    assert row[0] == 0
    assert 'MONSTER_DEFEATED' not in ('ITEM_ACQUISITION', 'ITEM_CONSUME_EFFECT')
