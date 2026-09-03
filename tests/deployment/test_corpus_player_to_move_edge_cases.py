"""Classification of corpus questions with no derivable player-to-move.

Audit outcome (42,804 records, measured against the real corpus):

    MALFORMED_METADATA_ESCAPED_BRACKET   36
    NO_MOVE_NO_PL                        13
    PARSER_INVALID                        4
    ------------------------------------ --
    TOTAL                                53

**Every one of the 53 has zero answer moves.** None was ever answerable, in any
mode, before or after the player-to-move repair.

Why there is no parser fix to make
----------------------------------
The 36 look like a parser bug and are not. Their content is shaped like::

    GN[模仿?第1題\\]PL[B]

Under the SGF specification ``\\]`` is an ESCAPED closing bracket, so the parser
is behaving correctly: ``GN``'s value is ``模仿?第1題]PL[B`` and the file
genuinely contains no ``PL`` property. Recovering the swallowed ``PL`` would mean
deliberately misparsing valid SGF escaping -- and would gain nothing, because
these records carry no answer tree either.

So this is authoring-time DATA debt, not an engine defect, and the correct
disposition is to leave canonical judging strict and defer the corpus repair.

Why fail-closed is the better outcome here
------------------------------------------
Before the repair these questions derived a colour from the literal ``PL[B]``
text inside the swallowed ``GN`` value, then judged every possible answer
INCORRECT (empty answer tree) and wrote a durable wrong-answer row. After the
repair they fail closed with ``judge_unavailable`` and write nothing. Failing
closed on an unanswerable question is strictly better than silently marking a
player wrong on it.

This module pins the classification so the numbers cannot drift unnoticed. It
skips when the corpus is absent, since ``questions.json`` is external content and
is deliberately not packaged into the image.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Measured 2026-09-03 against the 42,804-record corpus.
EXPECTED = {
    "MALFORMED_METADATA_ESCAPED_BRACKET": 36,
    "NO_MOVE_NO_PL": 13,
    "PARSER_INVALID": 4,
}
EXPECTED_TOTAL = 53
REPRESENTATIVE_IDS = {
    "MALFORMED_METADATA_ESCAPED_BRACKET": [71561, 71563, 71564, 71565, 50167, 50168],
    "NO_MOVE_NO_PL": [74535, 46389, 31706, 31707, 35389, 7965],
    "PARSER_INVALID": [71244, 40512, 70752, 65156],
}


def _corpus_path():
    for candidate in (
        os.environ.get("QUESTIONS_JSON_PATH"),
        str(REPO_ROOT / "questions.json"),
        r"D:/go-website/questions.json",
    ):
        if candidate and pathlib.Path(candidate).is_file():
            return pathlib.Path(candidate)
    return None


def _first_wins_index():
    """Index the corpus the way app.py resolves a question.

    ``app.py`` takes ``canonical_matches[0]``, i.e. the FIRST record with a given
    id. The corpus contains 11 duplicate ids, so a ``{q["id"]: q}`` comprehension
    is last-wins and disagrees with the runtime for exactly those records.
    """

    path = _corpus_path()
    index = {}
    for question in json.loads(path.read_text(encoding="utf-8")):
        index.setdefault(question["id"], question)
    return index


def _classify(content):
    from sgf_engine.parser.sgf_parser import parse_sgf

    try:
        root = parse_sgf(content, strict=True)
    except Exception:
        return "PARSER_INVALID", 0
    moves = [c for c in (root.children or []) if getattr(c, "move", None) is not None]
    colors = {c.move.color for c in moves if c.move.color in ("B", "W")}
    if not moves:
        escaped = "\\]" in content and "PL[" in content
        return ("MALFORMED_METADATA_ESCAPED_BRACKET" if escaped else "NO_MOVE_NO_PL"), 0
    if len(colors) != 1:
        return "AMBIGUOUS_FIRST_MOVE", len(moves)
    return "OTHER", len(moves)


@pytest.fixture(scope="module")
def classified():
    from guild_quest_answer_service import _question_player_to_move

    path = _corpus_path()
    if path is None:
        pytest.skip("questions.json is external content and is not present")

    corpus = json.loads(path.read_text(encoding="utf-8"))
    buckets = {}
    for question in corpus:
        content = question.get("content")
        if not isinstance(content, str) or not content.strip():
            buckets.setdefault("NO_CONTENT", []).append((question["id"], 0))
            continue
        if _question_player_to_move(content) is not None:
            continue
        category, move_count = _classify(content)
        buckets.setdefault(category, []).append((question["id"], move_count))
    return {"corpus_size": len(corpus), "buckets": buckets}


def test_classification_counts_have_not_drifted(classified):
    """CORPUS_EDGECASE_CLASSIFICATION."""

    actual = {k: len(v) for k, v in classified["buckets"].items()}
    assert actual == EXPECTED, (
        f"corpus edge-case classification drifted: {actual} != {EXPECTED}. "
        "Investigate before adjusting these numbers."
    )
    assert sum(actual.values()) == EXPECTED_TOTAL


def test_every_unresolved_question_is_unanswerable_anyway(classified):
    """The load-bearing fact: none of these carries an answer tree.

    This is why leaving them fail-closed costs no reachable gameplay.
    """

    for category, entries in classified["buckets"].items():
        for question_id, move_count in entries:
            assert move_count == 0, (
                f"question {question_id} ({category}) has {move_count} answer "
                "moves; it is answerable and must not be dismissed as data debt"
            )


def test_representative_ids_are_still_in_their_categories(classified):
    """Keeps the audit's worked examples honest against the live corpus."""

    for category, ids in REPRESENTATIVE_IDS.items():
        present = {qid for qid, _moves in classified["buckets"].get(category, [])}
        missing = [qid for qid in ids if qid not in present]
        assert missing == [], f"{category} lost representative ids {missing}"


def test_the_escaped_bracket_class_is_valid_sgf_not_a_parser_bug(classified):
    """The 36 must stay classified as DATA debt, never 'fix the parser'.

    ``\\]`` is a specification-mandated escaped bracket. If a future change makes
    the parser recover the swallowed PL, it is misparsing valid SGF.
    """

    from sgf_engine.parser.sgf_parser import parse_sgf

    corpus = _first_wins_index()
    sample = corpus[REPRESENTATIVE_IDS["MALFORMED_METADATA_ESCAPED_BRACKET"][0]]

    content = sample["content"]
    assert "\\]" in content, "sample must exercise the escaped-bracket shape"
    root = parse_sgf(content, strict=True)
    properties = root.metadata.get("properties", {})
    assert "PL" not in properties, (
        "the parser recovered a PL property from an escaped bracket; that is "
        "misparsing valid SGF escaping, not a repair"
    )
    assert "PL[" in properties["GN"][0], (
        "the PL text must remain part of the escaped GN value"
    )


def test_unresolved_questions_fail_closed_rather_than_judging(classified):
    """Fail-closed is preserved for every classified record."""

    from guild_quest_answer_service import (
        GuildQuestAnswerError,
        build_guild_quest_answer_context,
    )

    corpus = _first_wins_index()
    checked = 0
    for category, entries in classified["buckets"].items():
        for question_id, _moves in entries[:3]:
            with pytest.raises(GuildQuestAnswerError) as excinfo:
                build_guild_quest_answer_context(
                    corpus[question_id], "whole_board::LV2"
                )
            assert excinfo.value.code == "judge_unavailable"
            assert excinfo.value.status == 503
            checked += 1
    assert checked > 0


# Measured 2026-09-03: the corpus ships 11 ids that appear on more than one
# record, with DIFFERENT content. app.py resolves a question with
# ``canonical_matches[0]``, so the first record wins at runtime; any tooling that
# indexes with ``{q["id"]: q}`` is last-wins and will silently disagree with the
# application for exactly these ids.
EXPECTED_DUPLICATE_ID_COUNT = 11


def test_duplicate_corpus_ids_are_known_and_bounded():
    """Corpus data-integrity observation, deferred as data debt.

    Not a defect in the release under test -- the runtime is self-consistent
    because it always takes the first match -- but it is a real ambiguity in the
    content, and it silently breaks any last-wins index. Pinned so the count
    cannot grow unnoticed.
    """

    import collections

    path = _corpus_path()
    if path is None:
        pytest.skip("questions.json is external content and is not present")

    counts = collections.Counter(
        q["id"] for q in json.loads(path.read_text(encoding="utf-8"))
    )
    duplicates = {qid: n for qid, n in counts.items() if n > 1}
    assert len(duplicates) == EXPECTED_DUPLICATE_ID_COUNT, (
        f"duplicate corpus id count changed: {len(duplicates)} "
        f"(expected {EXPECTED_DUPLICATE_ID_COUNT}); sample {sorted(duplicates)[:5]}"
    )
