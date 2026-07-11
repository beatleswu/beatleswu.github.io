"""Strict 19x19 SGF coordinate and color helpers."""

from __future__ import annotations


_MIN_COORD = ord("a")
_MAX_COORD = ord("s")


def sgf_to_xy(sgf: str) -> tuple[int, int]:
    """Convert a lowercase SGF coordinate pair to zero-indexed ``(x, y)``."""
    if (
        not isinstance(sgf, str)
        or len(sgf) != 2
        or any(char < "a" or char > "s" for char in sgf)
    ):
        raise ValueError("SGF coordinate must be exactly two lowercase letters a-s.")
    return ord(sgf[0]) - _MIN_COORD, ord(sgf[1]) - _MIN_COORD


def xy_to_sgf(x: int, y: int) -> str:
    """Convert zero-indexed 19x19 coordinates to a lowercase SGF pair."""
    if type(x) is not int or type(y) is not int or not (0 <= x <= 18 and 0 <= y <= 18):
        raise ValueError("x and y must be integers in the range 0-18.")
    return chr(_MIN_COORD + x) + chr(_MIN_COORD + y)


def opponent_of(color: str) -> str:
    """Return the opposite color for strict SGF colors ``B`` and ``W``."""
    if color == "B":
        return "W"
    if color == "W":
        return "B"
    raise ValueError('color must be exactly "B" or "W".')

