"""LC002 track LC-A — deterministic fixtures + judge adapters.

Three judges are compared without being changed:

  A. map_battle_runtime.judge_map_battle_answer_v1
  B. Rating Test legacy: app._rt_parse_answer_tree / _rt_replay / _transform_sgf
     / _transform_point / _gtp_to_xy (the pure core of _rt_server_verify)
  C. sgf_engine deterministic engine: parser + matcher + autoreply
     (apply_move steps 2-5, minus the override-file load and the Postgres
     off-tree logger, neither of which can run in this tree)

Every adapter returns a normalized ``(verdict, reason)`` tuple. Verdicts are
NOT harmonized — the point of LC-A is to record where they differ.

All SGF here is hand-authored; nothing depends on questions.json.
"""

from __future__ import annotations

import sys
import types

# --------------------------------------------------------------------------
# app import (stub set shared with tests/test_adventure_boss_finish_server_authoritative.py)
# --------------------------------------------------------------------------

def install_app_import_stubs() -> None:
    """Stub the heavy transitive imports so `import app` is cheap.

    katago_explain and explain_overrides are deliberately NOT stubbed: they
    import fine on their own and LC-F needs the real modules. Stubbing them
    here made the suite order-dependent (LC-F picked up the stubs when run
    after LC-A/C/D).
    """
    from flask import Blueprint

    stubs = {
        "question_taxonomy": {"get_taxonomy": lambda *a, **k: {}},
        "monster_taxonomy": {
            "get_monster_taxonomy": lambda *a, **k: {},
            "mark_encounters": lambda *a, **k: None,
        },
        "chapter_i18n": {
            "localize_topic": lambda *a, **k: "",
            "localize_level": lambda *a, **k: "",
        },
        "backend_i18n": {
            "badge_en": lambda *a, **k: "",
            "skill_node_en": lambda *a, **k: "",
            "title_en": lambda *a, **k: "",
        },
    }
    for name, attrs in stubs.items():
        if name not in sys.modules:
            module = types.ModuleType(name)
            for key, value in attrs.items():
                setattr(module, key, value)
            sys.modules[name] = module
    if "grimoire_api" not in sys.modules:
        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("grimoire_stub_lc002", __name__)
        sys.modules["grimoire_api"] = module


# --------------------------------------------------------------------------
# coordinate helpers (a-s SGF, zero-indexed)
# --------------------------------------------------------------------------

def xy(coord: str) -> tuple[int, int]:
    return ord(coord[0]) - 97, ord(coord[1]) - 97


# 8-transform table — byte-identical in app.py and map_battle_runtime.py.
def transform_point(x: int, y: int, size: int, t: int) -> tuple[int, int]:
    n = size - 1
    fns = (
        lambda c, r: (c, r),
        lambda c, r: (n - r, c),
        lambda c, r: (n - c, n - r),
        lambda c, r: (r, n - c),
        lambda c, r: (n - c, r),
        lambda c, r: (c, n - r),
        lambda c, r: (r, c),
        lambda c, r: (n - r, n - c),
    )
    return fns[t](x, y)


# --------------------------------------------------------------------------
# Judge A — map_battle_runtime.judge_map_battle_answer_v1
# --------------------------------------------------------------------------

def judge_map_battle(
    sgf: str,
    moves_xy: list[tuple[int, int]],
    player_color: str = "B",
    *,
    size: int = 19,
    transform_id: str = "identity",
    accepted: list[dict] | None = None,
):
    from map_battle_runtime import CanonicalAnswer, judge_map_battle_answer_v1

    question: dict = {"content": sgf}
    if accepted is not None:
        question["accepted_moves"] = accepted
    attempt = {
        "board_size": size,
        "transform_id": transform_id,
        "player_color": player_color,
    }
    payload = {
        "player_color": player_color,
        "moves": [
            {"action": "play", "color": player_color, "x": x, "y": y}
            for (x, y) in moves_xy
        ],
    }
    canonical = CanonicalAnswer(payload=payload, result=None, reason_code="canonicalized")
    try:
        outcome = judge_map_battle_answer_v1(question, attempt, canonical)
    except Exception as error:  # JudgeUnavailable etc.
        return ("JUDGE_UNAVAILABLE", type(error).__name__)
    return (outcome.result, outcome.reason_code)


# --------------------------------------------------------------------------
# Judge B — Rating Test legacy pure core (mirrors _rt_server_verify order)
# --------------------------------------------------------------------------

def judge_rating(
    sgf: str,
    moves_xy: list[tuple[int, int]],
    player_color: str | None = None,   # deliberately unused by the real code
    *,
    transform: int = 0,
    accepted: list[dict] | None = None,
    katago_best_move: str | None = None,
    size: int = 19,
):
    import app

    sgf_t = app._transform_sgf(sgf, transform)
    moves = [{"x": x, "y": y} for (x, y) in moves_xy]

    # _rt_server_verify step 1: accepted_moves, compared UNTRANSFORMED.
    if accepted and len(moves) == 1:
        acc = {
            (m["x"], m["y"])
            for m in accepted
            if isinstance(m.get("x"), int) and isinstance(m.get("y"), int)
        }
        if (moves[0]["x"], moves[0]["y"]) in acc:
            return ("CORRECT", "accepted_move_untransformed")

    tree = app._rt_parse_answer_tree(sgf_t)
    if tree is not None and app._rt_replay(tree, moves):
        return ("CORRECT", "rt_replay")

    # _rt_server_verify step 3: KataGo best-move additive tolerance.
    if len(moves) == 1 and katago_best_move:
        bm = app._gtp_to_xy(katago_best_move, size)
        if bm:
            bx, by = app._transform_point(bm[0], bm[1], size, transform)
            if (moves[0]["x"], moves[0]["y"]) == (bx, by):
                return ("CORRECT", "katago_best_move_tolerance")

    if tree is None:
        return ("NO_VERDICT", "tree_none_client_boolean_trusted")
    return ("INCORRECT", "rt_replay")


# --------------------------------------------------------------------------
# Judge C — sgf_engine (apply_move steps 2-5, no override file, no DB)
# --------------------------------------------------------------------------

def judge_sgf_engine(
    sgf: str,
    moves_xy: list[tuple[int, int]],
    player_color: str = "B",
):
    from sgf_engine.core import autoreply, matcher
    from sgf_engine.core.coord_utils import xy_to_sgf
    from sgf_engine.core.tree import find_child_by_move
    from sgf_engine.parser.sgf_parser import parse_sgf

    try:
        current = parse_sgf(sgf, strict=True)
    except ValueError as error:
        return ("PARSE_FAIL", str(error)[:48])

    for (x, y) in moves_xy:
        coord = xy_to_sgf(x, y)
        result = matcher.match_move(current, coord, None)
        if result is matcher.OFF_TREE:
            return ("OFF_TREE", "matcher")
        # BRANCH (matcher/find_child_by_move are colour-blind; they key on coord)
        current = find_child_by_move(current, coord)
        reply = autoreply.get_auto_reply(current, player_color)
        if reply is not None:
            current = find_child_by_move(current, reply.coord)

    status = current.metadata.get("result", "continue")
    return (status, "leaf" if not current.children else "nonleaf")


ALL_JUDGES = {
    "map_battle": judge_map_battle,
    "rating": judge_rating,
    "sgf_engine": judge_sgf_engine,
}


# --------------------------------------------------------------------------
# Deterministic SGF fixtures
# --------------------------------------------------------------------------

# single correct root move -> terminal leaf
SGF_SINGLE_ROOT = "(;SZ[19];B[pd])"
# two authored root alternatives
SGF_TWO_ROOT_BRANCHES = "(;SZ[19](;B[pd])(;B[dp]))"
# player move, single deterministic opponent reply, player move, leaf
SGF_MULTI_MOVE = "(;SZ[19];B[pd];W[dd];B[qf])"
# player move then a single opponent reply that is itself a leaf
SGF_PLAYER_THEN_REPLY_LEAF = "(;SZ[19];B[pd];W[dd])"
# after B[pd] the tree offers TWO white replies (ambiguous auto-reply)
SGF_AMBIGUOUS_REPLY = "(;SZ[19];B[pd](;W[dd];B[qf])(;W[dp];B[cf]))"
# whole-board shape
SGF_WHOLE_BOARD = "(;SZ[19]AB[dd][pd][dp]AW[pp][pc][cp];B[qq])"
# local corner life-and-death shape
SGF_LOCAL_TSUMEGO = "(;SZ[19]AB[qa][ra][pb][pc][qd]AW[qb][rb][rc];B[sb])"
# setup only, no move node -> empty answer tree
SGF_EMPTY_TREE = "(;SZ[19]AB[dd][pd])"
# malformed: unbalanced parens
SGF_MALFORMED_UNBALANCED = "(;SZ[19];B[pd]"
# malformed: not an SGF at all
SGF_MALFORMED_GARBAGE = "garbage"
