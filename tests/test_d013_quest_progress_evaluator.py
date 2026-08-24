from __future__ import annotations

import pytest

from quest_catalog import (
    CANONICAL_QUEST_CATALOG,
    CURRENT_DAILY_DEFINITIONS,
    CatalogValidationError,
    QuestDefinition,
    build_catalog,
)
from quest_identity import resolve_quest_id
from quest_progress_evaluator import (
    AuthoritativeEvent,
    ClientEventAuthorityError,
    EventContractError,
    InvalidCompletionIdentity,
    ProgressDelta,
    UnknownEventType,
    evaluate_event,
    evaluate_quest_set_completion,
)


def _event(event_type: str, payload=None, event_id="evt-1", source_authority="server:test"):
    return AuthoritativeEvent.from_server(
        event_id=event_id,
        event_type=event_type,
        user_id=7,
        source_authority=source_authority,
        source_operation_id=f"op-{event_id}",
        occurred_at="2026-08-24T10:00:00+08:00",
        payload=payload or {},
    )


def _definition(
    quest_id: str,
    *,
    family="daily",
    period="daily",
    condition="QUESTION_CORRECT",
    filters=None,
    enabled=True,
    selection_group=None,
):
    _, quest_type = quest_id.split(":", 1)
    return QuestDefinition(
        quest_id=quest_id,
        quest_family=family,
        quest_type=quest_type,
        period=period,
        condition=condition,
        target=1,
        filters=filters or {},
        reward_profile_id=f"fixture:{quest_id}",
        availability={"catalog_status": "planned"},
        enabled=enabled,
        aliases=(),
        selection_group=selection_group,
    )


def test_event_envelope_is_immutable_and_requires_server_authority():
    event = _event("QUESTION_CORRECT", {"correct": True})
    with pytest.raises((AttributeError, TypeError)):
        event.event_id = "changed"
    with pytest.raises(TypeError):
        event.payload["correct"] = False
    with pytest.raises(ClientEventAuthorityError):
        _event("MONSTER_DEFEATED", source_authority="client")
    with pytest.raises(EventContractError):
        _event("MONSTER_DEFEATED", source_authority="anything")
    with pytest.raises(EventContractError):
        _event("QUEST_SET_COMPLETED", source_authority="quest_evaluator:fake")
    with pytest.raises(EventContractError):
        _event("QUESTION_CORRECT", {1: True})
    with pytest.raises(EventContractError):
        _event("QUESTION_CORRECT", {"correct": {True}})


def test_unknown_event_fails_closed_and_no_client_json_constructor_exists():
    with pytest.raises(UnknownEventType):
        _event("QUESTION_NOT_REAL")
    assert not hasattr(AuthoritativeEvent, "from_json")


def test_one_event_zero_quests():
    assert evaluate_event(_event("LOGIN_RECORDED")) == ()


def test_one_event_one_quest():
    catalog = build_catalog((_definition("weekly:answer", family="weekly", period="weekly"),))
    deltas = evaluate_event(_event("QUESTION_CORRECT", {"correct": True}), catalog)
    assert [delta.quest_id for delta in deltas] == ["weekly:answer"]
    assert deltas[0].operation == "INCREMENT"
    assert deltas[0].amount == 1
    assert deltas[0].period_key is None


def test_one_event_many_quests_across_families_use_one_engine():
    catalog = build_catalog(
        (
            _definition("achievement:answer_100", family="achievement", period="lifetime"),
            _definition("adventure:zone_03_answer", family="adventure", period="one_time", filters={"zone_key": "zone_03"}),
            _definition("weekly:answer", family="weekly", period="weekly"),
            _definition("daily:answer", family="daily", period="daily"),
        )
    )
    event = _event("QUESTION_CORRECT", {"correct": True, "zone_key": "zone_03"})
    assert [delta.quest_id for delta in evaluate_event(event, catalog)] == [
        "achievement:answer_100",
        "adventure:zone_03_answer",
        "daily:answer",
        "weekly:answer",
    ]


def test_disabled_quest_emits_no_delta():
    catalog = build_catalog((_definition("weekly:disabled", family="weekly", period="weekly", enabled=False),))
    assert evaluate_event(_event("QUESTION_CORRECT", {"correct": True}), catalog) == ()


def test_unknown_filter_is_rejected_by_d012_catalog():
    with pytest.raises(CatalogValidationError):
        build_catalog((_definition("daily:bad", filters={"unknown_filter": True}),))


def test_missing_payload_field_fails_closed_without_guessing():
    catalog = build_catalog(
        (
            _definition(
                "daily:dragon",
                filters={"correct": True, "monster_family": "dragon", "source_scope": "daily_battlefield"},
            ),
        )
    )
    assert evaluate_event(_event("QUESTION_CORRECT", {"correct": True}), catalog) == ()


def test_current_daily_kill_monsters_matches_authoritative_monster_event():
    deltas = evaluate_event(
        _event(
            "MONSTER_DEFEATED",
            {"source_scope": "daily_battlefield", "monster_id": "slime"},
        ),
        CANONICAL_QUEST_CATALOG,
    )
    assert [(delta.quest_id, delta.amount) for delta in deltas] == [("daily:kill_monsters", 1)]


def test_correct_dragon_matches_dragon_quest_and_incorrect_dragon_does_not():
    correct = _event(
        "QUESTION_CORRECT",
        {"correct": True, "monster_family": "dragon", "source_scope": "daily_battlefield"},
    )
    incorrect = _event(
        "QUESTION_CORRECT",
        {"correct": False, "monster_family": "dragon", "source_scope": "daily_battlefield"},
        event_id="evt-incorrect",
    )
    assert [delta.quest_id for delta in evaluate_event(correct, CANONICAL_QUEST_CATALOG)] == [
        "daily:challenge_dragon"
    ]
    assert not any(delta.quest_id == "daily:challenge_dragon" for delta in evaluate_event(incorrect, CANONICAL_QUEST_CATALOG))


def test_non_dragon_correct_does_not_match_dragon_quest():
    event = _event(
        "QUESTION_CORRECT",
        {"correct": True, "monster_family": "slime", "source_scope": "daily_battlefield"},
    )
    assert not any(delta.quest_id == "daily:challenge_dragon" for delta in evaluate_event(event, CANONICAL_QUEST_CATALOG))


def test_streak_correct_preserves_increment_and_reset_intent():
    correct = _event("QUESTION_CORRECT", {"correct": True, "streak_scope": "daily_consecutive"})
    incorrect = _event(
        "QUESTION_CORRECT",
        {"correct": False, "streak_scope": "daily_consecutive"},
        event_id="evt-wrong",
    )
    correct_delta = next(delta for delta in evaluate_event(correct, CANONICAL_QUEST_CATALOG) if delta.quest_id == "daily:streak_correct")
    reset_delta = next(delta for delta in evaluate_event(incorrect, CANONICAL_QUEST_CATALOG) if delta.quest_id == "daily:streak_correct")
    assert (correct_delta.operation, correct_delta.amount) == ("INCREMENT", 1)
    assert (reset_delta.operation, reset_delta.amount) == ("RESET", 0)
    assert "resets" in reset_delta.reason


def test_streak_reset_requires_non_correct_filters_to_match():
    catalog = build_catalog(
        (
            _definition(
                "daily:scoped_streak",
                filters={"correct": True, "streak_scope": "daily_consecutive", "source_scope": "daily"},
            ),
        )
    )
    wrong_scope = _event(
        "QUESTION_CORRECT",
        {"correct": False, "streak_scope": "daily_consecutive", "source_scope": "weekly"},
    )
    assert evaluate_event(wrong_scope, catalog) == ()


def test_filter_comparison_does_not_coerce_bool_and_integer_values():
    catalog = build_catalog(
        (
            _definition(
                "daily:strict_filter",
                condition="MONSTER_DEFEATED",
                filters={"monster_id": "1"},
            ),
        )
    )
    assert evaluate_event(_event("MONSTER_DEFEATED", {"monster_id": 1}), catalog) == ()


def test_quest_set_completion_is_derived_and_not_client_authoritative():
    with pytest.raises(EventContractError):
        _event("QUEST_SET_COMPLETED", {"quest_group": "daily_primary"})
    source = _event(
        "QUESTION_CORRECT",
        {"correct": True, "streak_scope": "daily_consecutive"},
        event_id="evt-third-primary",
    )
    completed = {definition.quest_id for definition in CURRENT_DAILY_DEFINITIONS if definition.selection_group == "daily_primary"}
    deltas = evaluate_quest_set_completion(
        source_event=source,
        completed_quest_ids=completed,
        catalog=CANONICAL_QUEST_CATALOG,
    )
    assert [(delta.quest_id, delta.operation, delta.amount) for delta in deltas] == [
        ("daily:all_complete", "INCREMENT", 3)
    ]


def test_quest_set_completion_requires_canonical_unique_ids():
    source = _event("QUESTION_CORRECT", {"correct": True})
    with pytest.raises(InvalidCompletionIdentity):
        evaluate_quest_set_completion(
            source_event=source,
            completed_quest_ids=("kill_monsters",),
            catalog=CANONICAL_QUEST_CATALOG,
        )
    with pytest.raises(InvalidCompletionIdentity):
        evaluate_quest_set_completion(
            source_event=source,
            completed_quest_ids=("daily:kill_monsters", "daily:kill_monsters"),
            catalog=CANONICAL_QUEST_CATALOG,
        )
    with pytest.raises(InvalidCompletionIdentity):
        evaluate_quest_set_completion(
            source_event=source,
            completed_quest_ids=("daily:not-a-quest",),
            catalog=CANONICAL_QUEST_CATALOG,
        )


def test_quest_set_completion_excludes_disabled_group_members():
    catalog = build_catalog(
        (
            _definition("daily:primary_enabled", selection_group="primary"),
            _definition("daily:primary_disabled", selection_group="primary", enabled=False),
            _definition(
                "daily:completion",
                condition="QUEST_SET_COMPLETED",
                filters={"quest_group": "primary"},
                selection_group="bonus",
            ),
        )
    )
    source = _event("QUESTION_CORRECT", {"correct": True})
    deltas = evaluate_quest_set_completion(
        source_event=source,
        completed_quest_ids={"daily:primary_enabled"},
        catalog=catalog,
    )
    assert [(delta.quest_id, delta.amount) for delta in deltas] == [("daily:completion", 1)]


def test_battlefield_boss_zone_and_spirit_filters_are_exact_and_anded():
    catalog = build_catalog(
        (
            _definition(
                "adventure:boss",
                family="adventure",
                period="one_time",
                condition="BATTLEFIELD_BOSS_DEFEATED",
                filters={"encounter_class": "battlefield_boss", "zone_key": "zone_03"},
            ),
            _definition(
                "achievement:fatty_stage_iii",
                family="achievement",
                period="lifetime",
                condition="SPIRIT_STAGE_REACHED",
                filters={"spirit_id": "fatty", "spirit_stage": "III"},
            ),
        )
    )
    assert [delta.quest_id for delta in evaluate_event(
        _event("BATTLEFIELD_BOSS_DEFEATED", {"encounter_class": "battlefield_boss", "zone_key": "zone_03"}), catalog
    )] == ["adventure:boss"]
    assert [delta.quest_id for delta in evaluate_event(
        _event("SPIRIT_STAGE_REACHED", {"spirit_id": "fatty", "spirit_stage": "III"}), catalog
    )] == ["achievement:fatty_stage_iii"]


def test_catalog_order_does_not_change_output_and_same_event_is_repeatable():
    definitions = (
        _definition("weekly:z", family="weekly", period="weekly"),
        _definition("daily:a"),
        _definition("achievement:m", family="achievement", period="lifetime"),
    )
    event = _event("QUESTION_CORRECT", {"correct": True}, event_id="stable-event")
    first = evaluate_event(event, build_catalog(definitions))
    second = evaluate_event(event, build_catalog(tuple(reversed(definitions))))
    assert first == second
    assert first == evaluate_event(event, build_catalog(definitions))


def test_matching_does_not_use_display_text_or_reward_value():
    first = _definition("weekly:one", family="weekly", period="weekly")
    second = _definition("weekly:two", family="weekly", period="weekly")
    first = QuestDefinition(**{**first.__dict__, "display_key": "title.one", "reward_profile_id": "reward:cheap"})
    second = QuestDefinition(**{**second.__dict__, "display_key": "title.two", "reward_profile_id": "reward:expensive"})
    deltas = evaluate_event(_event("QUESTION_CORRECT", {"correct": True}), build_catalog((second, first)))
    assert [delta.quest_id for delta in deltas] == ["weekly:one", "weekly:two"]


def test_d012_identity_resolver_and_blockers_are_preserved():
    assert resolve_quest_id("kill_monsters") == "daily:kill_monsters"
    from quest_catalog import QUEST_IDENTITY_BLOCKERS

    assert QUEST_IDENTITY_BLOCKERS == (
        "guild_segment_identity_requires_catalog_snapshot",
        "newbie_legacy_and_staged_ladders_require_explicit_migration_map",
    )


def test_progress_delta_model_is_single_pure_shape():
    delta = ProgressDelta(
        quest_id="daily:test",
        operation="INCREMENT",
        amount=1,
        source_event_id="evt",
        condition="QUESTION_CORRECT",
        reason="test",
        quest_family="daily",
        period="daily",
    )
    assert delta.period_key is None
    with pytest.raises(EventContractError):
        ProgressDelta(
            quest_id="daily:test",
            operation="RESET",
            amount=1,
            source_event_id="evt",
            condition="QUESTION_CORRECT",
            reason="test",
            quest_family="daily",
            period="daily",
        )
