import pytest

from sgf_engine.core.coord_utils import opponent_of, sgf_to_xy, xy_to_sgf


@pytest.mark.parametrize(
    ("coord", "expected"),
    [
        ("aa", (0, 0)),
        ("sa", (18, 0)),
        ("as", (0, 18)),
        ("ss", (18, 18)),
        ("dd", (3, 3)),
        ("pp", (15, 15)),
    ],
)
def test_sgf_to_xy_required_coordinates(coord, expected):
    assert sgf_to_xy(coord) == expected


def test_coordinate_round_trip():
    assert xy_to_sgf(*sgf_to_xy("qd")) == "qd"


@pytest.mark.parametrize(("color", "expected"), [("B", "W"), ("W", "B")])
def test_opponent(color, expected):
    assert opponent_of(color) == expected


@pytest.mark.parametrize("coord", ["QD", "a", "aaa", "az", "", 1, None])
def test_invalid_sgf_coordinate_raises(coord):
    with pytest.raises(ValueError):
        sgf_to_xy(coord)


@pytest.mark.parametrize(
    "coords",
    [
        (-1, 0),
        (19, 0),
        (0, -1),
        (0, 19),
        (True, 0),
        (0, True),
        (0, "1"),
        (1.5, 0),
        (0, None),
    ],
)
def test_invalid_xy_raises(coords):
    with pytest.raises(ValueError):
        xy_to_sgf(*coords)


@pytest.mark.parametrize("color", ["black", "white", 1, 0, None])
def test_invalid_opponent_color_raises(color):
    with pytest.raises(ValueError):
        opponent_of(color)
