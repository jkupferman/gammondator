from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


SAMPLE_PAYLOAD = {
    "position": {
        "points": [-2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2],
        "bar_white": 0,
        "bar_black": 0,
        "off_white": 0,
        "off_black": 0,
        "turn": "white",
        "cube_value": 1,
        "dice": [6, 1]
    },
    "played_move": {
        "notation": "24/18 13/7",
        "steps": [
            {"from_point": 24, "to_point": 18},
            {"from_point": 13, "to_point": 7}
        ]
    },
    "candidate_moves": [
        {
            "notation": "13/7 8/7",
            "steps": [
                {"from_point": 13, "to_point": 7},
                {"from_point": 8, "to_point": 7}
            ]
        },
        {
            "notation": "24/18 13/7",
            "steps": [
                {"from_point": 24, "to_point": 18},
                {"from_point": 13, "to_point": 7}
            ]
        },
        {
            "notation": "24/23 13/7",
            "steps": [
                {"from_point": 24, "to_point": 23},
                {"from_point": 13, "to_point": 7}
            ]
        }
    ]
}


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "backend": "heuristic"}


def test_analyze_move_returns_ranked_feedback() -> None:
    response = client.post("/analyze-move", json=SAMPLE_PAYLOAD)
    assert response.status_code == 200

    data = response.json()
    assert "best_move" in data
    assert "played_move" in data
    assert len(data["top_moves"]) == 3
    assert data["played_move"]["delta_vs_best"] >= 0
    assert isinstance(data["played_move"]["why"], list)


def test_analyzer_info() -> None:
    response = client.get("/analyzer")
    assert response.status_code == 200
    data = response.json()
    assert data["backend"] == "heuristic"
    assert data["fallback_active"] is False
    assert isinstance(data["details"], str)


def test_choose_ai_move() -> None:
    payload = {
        "position": SAMPLE_PAYLOAD["position"],
        "candidate_moves": SAMPLE_PAYLOAD["candidate_moves"],
    }
    response = client.post("/choose-ai-move", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "selected_move" in data
    assert len(data["top_moves"]) == 3
    assert data["selected_move"]["delta_vs_best"] == 0


def test_legal_moves_endpoint_returns_moves() -> None:
    response = client.post("/legal-moves", json={"position": SAMPLE_PAYLOAD["position"]})
    assert response.status_code == 200
    data = response.json()
    assert len(data["moves"]) > 0
    assert "notation" in data["moves"][0]


def test_choose_ai_move_from_position() -> None:
    response = client.post(
        "/choose-ai-move-from-position",
        json={"position": SAMPLE_PAYLOAD["position"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "selected_move" in data
    assert len(data["top_moves"]) > 0


def test_choose_ai_move_from_position_when_no_legal_moves() -> None:
    points = [0] * 24
    points[22] = -2
    points[23] = -2
    payload = {
        "position": {
            "points": points,
            "bar_white": 1,
            "bar_black": 0,
            "off_white": 14,
            "off_black": 11,
            "turn": "white",
            "cube_value": 1,
            "dice": [1, 2],
        }
    }
    response = client.post("/choose-ai-move-from-position", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "no legal moves available"
