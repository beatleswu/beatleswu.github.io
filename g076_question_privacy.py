"""G076 board-only SGF projection. No scoring, accounts or persistence.

This is only a safe *display* contract. Never treat the presence of this
module as proof that the site's old full-answer endpoints are protected.
Turning on global enforcement requires all legacy consumers to migrate.
"""
from sgf_point_transform import _properties

# Setup stones, board size, side to move and question annotations only.
# Deliberately excludes solution variations, hints, comments and analysis.
_BOARD_PROPERTIES = frozenset(("SZ", "AB", "AW", "AE", "PL", "LB",
                               "TR", "SQ", "CR", "MA"))
_NON_SETUP_MOVE_PROPERTIES = frozenset(("B", "W"))


def privacy_enforced(environ):
    """Explicit rollout gate, default OFF. Unknown values fail OFF."""
    return str(environ.get("G076_ANSWER_PRIVACY_ENFORCED", "")).strip().lower() in (
        "1", "true", "on",
    )


def board_only_sgf(source):
    """Return a parseable SGF with only the initial board state/labels.

    Parse every property first, so malformed trees/escaped delimiters fail
    closed instead of leaking after a naive split(';') or regex. Root B/W
    moves are ambiguous (could be the correct answer) and must not be served.
    """
    if not isinstance(source, str) or len(source) > 1000000:
        raise ValueError("question_preview_unavailable")
    tokens = list(_properties(source))
    if not tokens or any(game != 0 for game, node, name, start, end in tokens):
        raise ValueError("question_preview_unavailable")
    root = [(name, source[start:end]) for game, node, name, start, end
            in tokens if node == 0]
    if not root:
        raise ValueError("question_preview_unavailable")
    if any(name in _NON_SETUP_MOVE_PROPERTIES for name, _ in root):
        raise ValueError("ambiguous_root_move")
    sizes = [value for name, value in root if name == "SZ"]
    if len(sizes) > 1 or (sizes and (
            not sizes[0].isascii() or not sizes[0].isdigit()
            or not 2 <= int(sizes[0]) <= 25
    )):
        raise ValueError("unsupported_board_size")
    players = [value for name, value in root if name == "PL"]
    if len(players) > 1 or any(value not in ("B", "W") for value in players):
        raise ValueError("invalid_player_to_move")
    props = [(name, value) for name, value in root if name in _BOARD_PROPERTIES]
    # Mirror the existing WGo board's default 19-line board when SZ is absent.
    if not sizes:
        props.insert(0, ("SZ", "19"))
    # Legacy browser derives side-to-play from the FIRST solution move if PL
    # is missing. Preserve only the colour, never its coordinate/variation.
    if not players:
        first_colour = next(
            (name for game, node, name, start, end in tokens
             if node > 0 and name in _NON_SETUP_MOVE_PROPERTIES),
            "B",
        )
        props.append(("PL", first_colour))
    return "(;" + "".join(f"{name}[{value}]" for name, value in props) + ")"
