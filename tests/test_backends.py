from __future__ import annotations

import os
import sys

import pytest

from app.backends import (
    AnalyzerBackend,
    BackendRuntime,
    BackendUnavailableError,
    GnuBGBridgeBackend,
    HeuristicBackend,
    load_backend,
)
from app.schemas import AnalyzeMoveRequest


def _sample_request() -> AnalyzeMoveRequest:
    return AnalyzeMoveRequest.model_validate(
        {
            "position": {
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
            },
            "played_move": {
                "notation": "24/18 13/7",
                "steps": [
                    {"from_point": 24, "to_point": 18},
                    {"from_point": 13, "to_point": 7},
                ],
            },
            "candidate_moves": [
                {
                    "notation": "13/7 8/7",
                    "steps": [
                        {"from_point": 13, "to_point": 7},
                        {"from_point": 8, "to_point": 7},
                    ],
                },
                {
                    "notation": "24/18 13/7",
                    "steps": [
                        {"from_point": 24, "to_point": 18},
                        {"from_point": 13, "to_point": 7},
                    ],
                },
                {
                    "notation": "24/23 13/7",
                    "steps": [
                        {"from_point": 24, "to_point": 23},
                        {"from_point": 13, "to_point": 7},
                    ],
                },
            ],
        }
    )


def test_gnubg_bridge_backend_contract() -> None:
    backend = GnuBGBridgeBackend(f"{sys.executable} scripts/gnubg_bridge_stub.py")
    response = backend.analyze_move(_sample_request())

    assert response.best_move.delta_vs_best == 0
    assert len(response.top_moves) == 3


def test_load_backend_falls_back_to_heuristic_when_missing_bridge(monkeypatch) -> None:
    monkeypatch.setenv("GAMMONDATOR_ANALYZER", "gnubg")
    monkeypatch.setenv("GAMMONDATOR_GNUBG_BRIDGE_CMD", "definitely-not-a-real-executable")
    monkeypatch.delenv("GAMMONDATOR_FALLBACK_TO_HEURISTIC", raising=False)

    runtime = load_backend()

    assert runtime.backend.name == "heuristic"
    assert runtime.fallback_active is True


def test_load_backend_gnubg_without_fallback_raises(monkeypatch) -> None:
    monkeypatch.setenv("GAMMONDATOR_ANALYZER", "gnubg")
    monkeypatch.setenv("GAMMONDATOR_GNUBG_BRIDGE_CMD", "definitely-not-a-real-executable")
    monkeypatch.setenv("GAMMONDATOR_FALLBACK_TO_HEURISTIC", "0")

    with pytest.raises(BackendUnavailableError):
        load_backend()


def test_runtime_fallback_on_primary_backend_error() -> None:
    class FailingBackend(AnalyzerBackend):
        name = "failing"

        def analyze_move(self, request):  # noqa: ANN001
            raise BackendUnavailableError("boom")

    runtime = BackendRuntime(
        backend=FailingBackend(),
        configured="gnubg",
        fallback_active=False,
        details="test",
        fallback_backend=HeuristicBackend(),
    )

    response = runtime.analyze_move(_sample_request())
    assert response.best_move.delta_vs_best == 0


@pytest.mark.skipif(
    not os.path.exists("/opt/local/bin/gnubg"),
    reason="GNU Backgammon binary not available at /opt/local/bin/gnubg",
)
def test_real_gnubg_bridge_backend_contract() -> None:
    backend = GnuBGBridgeBackend(f"{sys.executable} scripts/gnubg_bridge_real.py", timeout_seconds=30.0)
    response = backend.analyze_move(_sample_request())

    assert response.best_move.delta_vs_best == 0
    assert len(response.top_moves) == 3
