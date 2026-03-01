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


def test_session_lifecycle_and_play_turn() -> None:
    create_response = client.post(
        "/sessions",
        json={"initial_position": SAMPLE_PAYLOAD["position"]},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    session_id = created["session_id"]
    assert created["move_count"] == 0
    assert created["current_position"]["turn"] == "white"

    get_response = client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200
    state = get_response.json()
    assert state["session_id"] == session_id
    assert state["move_count"] == 0

    play_response = client.post(
        f"/sessions/{session_id}/play-turn",
        json={
            "played_move": {
                "notation": "24/18 8/7",
                "steps": [
                    {"from_point": 24, "to_point": 18},
                    {"from_point": 8, "to_point": 7},
                ],
            },
            "next_dice": [3, 2],
            "record_training": True,
        },
    )
    assert play_response.status_code == 200
    played = play_response.json()
    assert played["session_id"] == session_id
    assert played["move_count"] == 1
    assert played["analysis"]["played_move"]["notation"] == "24/18 8/7"
    assert played["current_position"]["turn"] == "black"
    assert played["current_position"]["dice"] == [3, 2]


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


def test_analyze_position() -> None:
    response = client.post("/analyze-position", json={"position": SAMPLE_PAYLOAD["position"]})
    assert response.status_code == 200
    data = response.json()
    assert "best_move" in data
    assert len(data["top_moves"]) > 0
    assert data["legal_move_count"] >= len(data["top_moves"])


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


def test_rate_played_move_from_position() -> None:
    payload = {
        "position": SAMPLE_PAYLOAD["position"],
        "played_move": {
            "notation": "24/18 8/7",
            "steps": [
                {"from_point": 24, "to_point": 18},
                {"from_point": 8, "to_point": 7},
            ],
        },
    }
    response = client.post("/rate-played-move", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "best_move" in data
    assert "played_move" in data


def test_rate_played_move_rejects_illegal_play() -> None:
    payload = {
        "position": SAMPLE_PAYLOAD["position"],
        "played_move": {
            "notation": "24/24",
            "steps": [{"from_point": 24, "to_point": 24}],
        },
    }
    response = client.post("/rate-played-move", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "played_move is not legal for this position/dice"


def test_rate_played_move_and_record_and_training_views() -> None:
    payload = {
        "position": SAMPLE_PAYLOAD["position"],
        "played_move": {
            "notation": "24/18 8/7",
            "steps": [
                {"from_point": 24, "to_point": 18},
                {"from_point": 8, "to_point": 7},
            ],
        },
    }
    response = client.post("/rate-played-move-and-record", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["review_id"], int)
    assert "analysis" in data

    summary_response = client.get("/training/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_moves"] >= 1
    assert "average_equity_loss" in summary

    mistakes_response = client.get("/training/mistakes?limit=5")
    assert mistakes_response.status_code == 200
    mistakes = mistakes_response.json()["mistakes"]
    assert isinstance(mistakes, list)
    assert len(mistakes) >= 1
    assert "leak_category" in mistakes[0]

    leaks_response = client.get("/training/leaks")
    assert leaks_response.status_code == 200
    leaks = leaks_response.json()["leaks"]
    assert isinstance(leaks, list)
    assert len(leaks) >= 1
    assert "leak_category" in leaks[0]
