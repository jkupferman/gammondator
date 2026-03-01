from app.movegen import generate_legal_moves
from app.schemas import Position


def test_generate_legal_moves_returns_moves_for_standard_position() -> None:
    position = Position.model_validate(
        {
            "points": [
                -2,
                0,
                0,
                0,
                0,
                5,
                0,
                3,
                0,
                0,
                0,
                -5,
                5,
                0,
                0,
                0,
                -3,
                0,
                -5,
                0,
                0,
                0,
                0,
                2,
            ],
            "bar_white": 0,
            "bar_black": 0,
            "off_white": 0,
            "off_black": 0,
            "turn": "white",
            "cube_value": 1,
            "dice": [6, 1],
        }
    )

    moves = generate_legal_moves(position)

    assert len(moves) > 0
    assert all(move.steps for move in moves)


def test_generate_legal_moves_supports_bar_entries() -> None:
    position = Position.model_validate(
        {
            "points": [0] * 24,
            "bar_white": 1,
            "bar_black": 0,
            "off_white": 14,
            "off_black": 15,
            "turn": "white",
            "cube_value": 1,
            "dice": [1, 2],
        }
    )

    moves = generate_legal_moves(position)
    notations = {move.notation for move in moves}

    assert "bar/23 23/22" in notations
    assert "bar/24 24/22" in notations


def test_generate_legal_moves_returns_empty_when_bar_blocked() -> None:
    points = [0] * 24
    points[22] = -2
    points[23] = -2

    position = Position.model_validate(
        {
            "points": points,
            "bar_white": 1,
            "bar_black": 0,
            "off_white": 14,
            "off_black": 11,
            "turn": "white",
            "cube_value": 1,
            "dice": [1, 2],
        }
    )

    assert generate_legal_moves(position) == []
