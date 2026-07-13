import community_leaderboard_rewards as lbr


def test_rank_leaderboard_participants_uses_score_then_final_timestamp_then_user_id():
    rows = [
        {
            "id": 3,
            "username": "u3",
            "display_name": "U3",
            "score": 10,
            "final_counted_at": "2026-07-06T03:00:00",
        },
        {
            "id": 2,
            "username": "u2",
            "display_name": "U2",
            "score": 10,
            "final_counted_at": "2026-07-06T02:00:00",
        },
        {
            "id": 1,
            "username": "u1",
            "display_name": "U1",
            "score": 10,
            "final_counted_at": "2026-07-06T02:00:00",
        },
    ]
    ranked = lbr.rank_leaderboard_participants(rows)
    assert [row["user_id"] for row in ranked] == [1, 2, 3]
    assert [row["rank"] for row in ranked] == [1, 2, 3]


def test_summarize_preview_rewards_counts_only_rewarded_claim_rows():
    preview_entries = [
        {
            "eligible": True,
            "reward_payload": {"coins": 500, "items": {"xp_potion": 2}, "badges": ["badge_lb_weekly_1"], "titles": []},
        },
        {
            "eligible": False,
            "reward_payload": {"coins": 0, "items": {}, "badges": [], "titles": []},
        },
    ]
    summary = lbr.summarize_preview_rewards(preview_entries)
    assert summary["claims_count"] == 1
    assert summary["snapshot_row_count"] == 2
    assert summary["eligible_claim_count"] == 1
    assert summary["non_rewarded_row_count"] == 1
    assert summary["component_count"] == 3
