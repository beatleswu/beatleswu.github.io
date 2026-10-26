"""Reuse the d0 public-practice SGF judge. No copied judging implementation."""
from .service import CourseError


def existing_practice_judge(load_question):
    def judge(user, item, moves):
        from practice_answer_authority import canonicalize_practice_answer, judge_practice_answer, PracticeAttemptError
        from map_battle_runtime import question_revision_for
        question = load_question(item["canonical_id"])
        if not question or question_revision_for(question) != item["revision"]:
            raise CourseError("question_revision_changed")
        attempt = {"nonce": "g066-server-judging", "source_record_uuid": item["canonical_id"],
                   "question_revision": item["revision"], "board_size": question["board_size"],
                   "player_color": question["player_color"], "transform_id": "identity"}
        try:
            answer = canonicalize_practice_answer({"moves": moves}, attempt)
            return judge_practice_answer(question, attempt, answer).result
        except PracticeAttemptError as exc:
            raise CourseError(exc.code, exc.status) from exc
    return judge


def existing_coin_reward(*, coins, owner_approved=False):
    """Optional existing ACT-C authority bridge; XP policy remains undecided/OFF."""
    if not owner_approved or type(coins) is not int or coins < 0:
        raise ValueError("explicit Owner-approved server reward amount required")

    def reward(conn, user, stage_key):
        from coin_reward_authority import settle_rewards_sync_claim_in_transaction
        return settle_rewards_sync_claim_in_transaction(
            conn, user_id=user, stage_key=stage_key,
            server_computed_coins=coins, server_computed_xp=0)
    return reward
