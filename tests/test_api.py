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
        "notation": "24/18 8/7",
        "steps": [
            {"from_point": 24, "to_point": 18},
            {"from_point": 8, "to_point": 7}
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
            "notation": "24/18 8/7",
            "steps": [
                {"from_point": 24, "to_point": 18},
                {"from_point": 8, "to_point": 7}
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


def test_web_index() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_session_lifecycle_and_play_turn() -> None:
    create_response = client.post(
        "/sessions",
        json={"initial_position": SAMPLE_PAYLOAD["position"]},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    session_id = created["session_id"]
    assert created["profile_id"] == "default"
    assert created["move_count"] == 0
    assert created["current_position"]["turn"] == "white"

    get_response = client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200
    state = get_response.json()
    assert state["session_id"] == session_id
    assert state["profile_id"] == "default"
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

    report_response = client.get(f"/sessions/{session_id}/report?top_n=3")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["session_id"] == session_id
    assert report["total_turns"] >= 1
    assert isinstance(report["top_mistakes"], list)

    turns_response = client.get(f"/sessions/{session_id}/turns")
    assert turns_response.status_code == 200
    turns_payload = turns_response.json()
    assert turns_payload["session_id"] == session_id
    assert len(turns_payload["turns"]) >= 1
    assert turns_payload["turns"][0]["actor"] == "human"
    assert "played_notation" in turns_payload["turns"][0]

    close_response = client.post(f"/sessions/{session_id}/close")
    assert close_response.status_code == 200
    assert close_response.json()["status"] == "completed"

    rejected_play = client.post(
        f"/sessions/{session_id}/play-turn",
        json={
            "played_move": {
                "notation": "24/18 8/7",
                "steps": [
                    {"from_point": 24, "to_point": 18},
                    {"from_point": 8, "to_point": 7},
                ],
            },
            "record_training": True,
        },
    )
    assert rejected_play.status_code == 400
    assert "not active" in rejected_play.json()["detail"]


def test_session_ai_turn() -> None:
    create_response = client.post(
        "/sessions",
        json={"initial_position": SAMPLE_PAYLOAD["position"]},
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/sessions/{session_id}/ai-turn",
        json={"next_dice": [4, 2], "apply_move": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["move_count"] == 1
    assert "selected_move" in data
    assert "selected_play" in data
    assert len(data["selected_play"]["steps"]) >= 1
    assert len(data["top_moves"]) > 0
    assert data["current_position"]["turn"] == "black"
    assert data["current_position"]["dice"] == [4, 2]

    turns_response = client.get(f"/sessions/{session_id}/turns")
    assert turns_response.status_code == 200
    turns = turns_response.json()["turns"]
    assert len(turns) >= 1
    assert turns[-1]["actor"] == "ai"


def test_session_ai_turn_preview_only() -> None:
    create_response = client.post(
        "/sessions",
        json={"initial_position": SAMPLE_PAYLOAD["position"]},
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/sessions/{session_id}/ai-turn",
        json={"apply_move": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["current_position"] is None
    assert len(data["selected_play"]["steps"]) >= 1
    assert data["move_count"] == 0


def test_session_roll_endpoint() -> None:
    create_response = client.post(
        "/sessions",
        json={"initial_position": SAMPLE_PAYLOAD["position"]},
    )
    session_id = create_response.json()["session_id"]
    response = client.post(f"/sessions/{session_id}/roll")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert 1 <= data["dice"][0] <= 6
    assert 1 <= data["dice"][1] <= 6
    assert data["position"]["dice"] == data["dice"]


def test_session_turns_not_found() -> None:
    response = client.get("/sessions/999999/turns")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_session_turns_markdown_not_found() -> None:
    response = client.get("/sessions/999999/turns/markdown")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_session_turns_markdown_endpoint() -> None:
    create_response = client.post(
        "/sessions",
        json={"initial_position": SAMPLE_PAYLOAD["position"]},
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["session_id"]
    play_response = client.post(
        f"/sessions/{session_id}/play-turn",
        json={
            "played_move": SAMPLE_PAYLOAD["played_move"],
            "next_dice": [3, 2],
            "record_training": True,
        },
    )
    assert play_response.status_code == 200

    response = client.get(f"/sessions/{session_id}/turns/markdown")
    assert response.status_code == 200
    body = response.text
    assert f"# Session {session_id} Turn Timeline" in body
    assert "Played: 24/18 8/7" in body


def test_list_sessions_by_profile() -> None:
    client.post("/sessions", json={"initial_position": SAMPLE_PAYLOAD["position"], "profile_id": "alpha"})
    client.post("/sessions", json={"initial_position": SAMPLE_PAYLOAD["position"], "profile_id": "beta"})
    alpha = client.get("/sessions?profile_id=alpha")
    beta = client.get("/sessions?profile_id=beta")
    assert alpha.status_code == 200
    assert beta.status_code == 200
    assert all(s["profile_id"] == "alpha" for s in alpha.json()["sessions"])
    assert all(s["profile_id"] == "beta" for s in beta.json()["sessions"])


def test_analyze_move_returns_ranked_feedback() -> None:
    response = client.post("/analyze-move", json=SAMPLE_PAYLOAD)
    assert response.status_code == 200

    data = response.json()
    assert "best_move" in data
    assert "played_move" in data
    assert len(data["top_moves"]) == 3
    assert data["played_move"]["delta_vs_best"] >= 0
    assert isinstance(data["played_move"]["why"], list)


def test_analyze_move_rejects_illegal_candidate() -> None:
    payload = {
        **SAMPLE_PAYLOAD,
        "candidate_moves": [
            {
                "notation": "24/24",
                "steps": [{"from_point": 24, "to_point": 24}],
            }
        ],
    }
    response = client.post("/analyze-move", json=payload)
    assert response.status_code == 400
    assert "candidate move is not legal" in response.json()["detail"]


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


def test_choose_ai_move_rejects_illegal_candidate() -> None:
    payload = {
        "position": SAMPLE_PAYLOAD["position"],
        "candidate_moves": [
            {
                "notation": "24/24",
                "steps": [{"from_point": 24, "to_point": 24}],
            }
        ],
    }
    response = client.post("/choose-ai-move", json=payload)
    assert response.status_code == 400
    assert "candidate move is not legal" in response.json()["detail"]


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

    other_profile_summary = client.get("/training/summary?profile_id=other")
    assert other_profile_summary.status_code == 200
    assert other_profile_summary.json()["total_moves"] == 0

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

    drills_response = client.get("/training/drills?limit=5")
    assert drills_response.status_code == 200
    drills = drills_response.json()["drills"]
    assert len(drills) >= 1
    review_id = drills[0]["review_id"]

    attempt_response = client.post(
        "/training/drills/attempt",
        json={
            "review_id": review_id,
            "chosen_notation": drills[0]["best_notation"],
        },
    )
    assert attempt_response.status_code == 200
    attempt = attempt_response.json()
    assert attempt["correct"] is True

    drill_summary_response = client.get("/training/drills/summary")
    assert drill_summary_response.status_code == 200
    summary = drill_summary_response.json()
    assert summary["total_attempts"] >= 1
    assert 0 <= summary["accuracy"] <= 1


def test_cube_decision_endpoint() -> None:
    payload = {"position": SAMPLE_PAYLOAD["position"], "action": "nodouble"}
    response = client.post("/cube/decision", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_action"] in {"double", "nodouble", "take", "pass"}
    assert data["quality"] in {"excellent", "good", "inaccuracy", "mistake", "blunder"}
    assert isinstance(data["why"], list)


def test_analysis_job_queue_flow() -> None:
    create = client.post(
        "/analysis-jobs",
        json={
            "profile_id": "default",
            "analysis_mode": "deep",
            "position": SAMPLE_PAYLOAD["position"],
        },
    )
    assert create.status_code == 200
    created = create.json()
    job_id = created["job_id"]
    assert created["status"] == "pending"
    assert created["analysis_mode"] == "deep"

    run = client.post(f"/analysis-jobs/{job_id}/run")
    assert run.status_code == 200
    ran = run.json()
    assert ran["job_id"] == job_id
    assert ran["status"] in {"completed", "failed"}
    if ran["status"] == "completed":
        assert ran["result"] is not None

    fetch = client.get(f"/analysis-jobs/{job_id}")
    assert fetch.status_code == 200
    fetched = fetch.json()
    assert fetched["job_id"] == job_id


def test_analysis_job_run_next() -> None:
    client.post("/analysis-jobs", json={"profile_id": "default", "position": SAMPLE_PAYLOAD["position"]})
    run_next = client.post("/analysis-jobs/run-next?profile_id=default")
    assert run_next.status_code == 200
    payload = run_next.json()
    assert payload["status"] in {"completed", "failed"}


def test_analysis_job_run_batch() -> None:
    client.post("/analysis-jobs", json={"profile_id": "default", "position": SAMPLE_PAYLOAD["position"]})
    client.post("/analysis-jobs", json={"profile_id": "default", "position": SAMPLE_PAYLOAD["position"]})
    batch = client.post("/analysis-jobs/run-batch?profile_id=default&limit=5")
    assert batch.status_code == 200
    data = batch.json()
    assert data["processed"] >= 2
    assert data["completed"] + data["failed"] == data["processed"]
    assert len(data["job_ids"]) == data["processed"]


def test_analysis_job_retry() -> None:
    created = client.post(
        "/analysis-jobs",
        json={"profile_id": "default", "position": SAMPLE_PAYLOAD["position"]},
    ).json()
    job_id = created["job_id"]
    client.post(f"/analysis-jobs/{job_id}/run")
    retry = client.post(f"/analysis-jobs/{job_id}/retry")
    assert retry.status_code == 200
    payload = retry.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "pending"


def test_analysis_job_stats_endpoint() -> None:
    client.post("/analysis-jobs", json={"profile_id": "stats-user", "position": SAMPLE_PAYLOAD["position"]})
    stats = client.get("/analysis-jobs/stats?profile_id=stats-user")
    assert stats.status_code == 200
    data = stats.json()
    assert data["profile_id"] == "stats-user"
    assert data["pending"] >= 1
    assert data["running"] >= 0
    assert data["completed"] >= 0
    assert data["failed"] >= 0


def test_analysis_job_cleanup_endpoints() -> None:
    created = client.post(
        "/analysis-jobs",
        json={"profile_id": "cleanup-user", "position": SAMPLE_PAYLOAD["position"]},
    ).json()
    job_id = created["job_id"]

    # Pending jobs cannot be deleted directly.
    reject_delete = client.delete(f"/analysis-jobs/{job_id}")
    assert reject_delete.status_code == 400

    # Run and then delete.
    client.post(f"/analysis-jobs/{job_id}/run")
    ok_delete = client.delete(f"/analysis-jobs/{job_id}")
    assert ok_delete.status_code == 200
    assert ok_delete.json()["deleted"] == 1

    # Bulk cleanup should succeed and return an integer.
    cleanup = client.post("/analysis-jobs/cleanup?profile_id=cleanup-user")
    assert cleanup.status_code == 200
    assert cleanup.json()["deleted"] >= 0


def test_training_dashboard_endpoint() -> None:
    response = client.get("/training/dashboard?profile_id=default")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "leaks" in data
    assert "drill_summary" in data
    assert "recent_jobs" in data


def test_training_report_endpoint() -> None:
    response = client.get("/training/report?profile_id=default")
    assert response.status_code == 200
    data = response.json()
    assert data["profile_id"] == "default"
    assert "summary" in data
    assert "leaks" in data
    assert "drill_summary" in data
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) >= 1


def test_training_report_markdown_endpoint() -> None:
    response = client.get("/training/report/markdown?profile_id=default")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    text = response.text
    assert "# Gammondator Training Report (default)" in text
    assert "## Summary" in text
    assert "## Recommendations" in text
