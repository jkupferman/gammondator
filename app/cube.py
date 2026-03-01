from __future__ import annotations

import os
import re
import subprocess

from app.analysis import _evaluate
from app.movegen import PositionState
from app.schemas import CubeDecisionRequest, CubeDecisionResponse

PROPER_ACTION_PATTERN = re.compile(r"Proper cube action:\s*(.+)")


def _quality(delta: float) -> str:
    if delta <= 0.01:
        return "excellent"
    if delta <= 0.04:
        return "good"
    if delta <= 0.10:
        return "inaccuracy"
    if delta <= 0.20:
        return "mistake"
    return "blunder"


def _recommend_action(equity: float, action: str) -> tuple[str, float]:
    # Approximate cube thresholds (money-game style) for MVP coaching.
    if action in {"double", "nodouble"}:
        if equity >= 0.20:
            return "double", equity - 0.20
        return "nodouble", 0.20 - equity

    # take/pass branch (facing a double)
    if equity >= -0.60:
        return "take", equity + 0.60
    return "pass", -0.60 - equity


def _state_to_simple_board_numbers(state: PositionState) -> list[int]:
    return [state.bar_white, *state.points, state.bar_black]


def _run_gnubg_cube_eval(state: PositionState) -> str | None:
    if os.getenv("GAMMONDATOR_CUBE_ENGINE", "1") == "0":
        return None

    gnubg_bin = os.getenv("GNUBG_BIN", "/opt/local/bin/gnubg")
    if not os.path.exists(gnubg_bin):
        return None

    board_args = " ".join(str(value) for value in _state_to_simple_board_numbers(state))
    commands = "\n".join(
        [
            "new game",
            f"set board simple {board_args}",
            "set turn jonathan",
            "eval",
            "quit",
            "",
        ]
    )

    proc = subprocess.run(
        [gnubg_bin, "-t"],
        input=commands,
        text=True,
        capture_output=True,
        timeout=float(os.getenv("GAMMONDATOR_GNUBG_TIMEOUT", "15")),
        check=False,
    )
    if proc.returncode != 0:
        return None

    match = PROPER_ACTION_PATTERN.search(proc.stdout)
    if not match:
        return None
    return match.group(1).strip()


def _map_proper_action(proper_action: str, action_context: str) -> str:
    normalized = proper_action.lower()
    if action_context in {"double", "nodouble"}:
        return "double" if normalized.startswith("double") else "nodouble"
    if "double, pass" in normalized:
        return "pass"
    if "double, take" in normalized:
        return "take"
    return "take"


def evaluate_cube_decision(request: CubeDecisionRequest) -> CubeDecisionResponse:
    state = PositionState.from_position(request.position)
    cubeless_equity, features = _evaluate(state, request.position.turn)

    proper_action = _run_gnubg_cube_eval(state)
    if proper_action is not None:
        recommended = _map_proper_action(proper_action, request.action)
        edge = 0.0 if recommended == request.action else 0.12
        engine_note = f"GNUbg proper cube action: {proper_action}."
    else:
        recommended, edge = _recommend_action(cubeless_equity, request.action)
        engine_note = "GNUbg cube action unavailable; used heuristic thresholds."
    delta = abs(edge) if request.action != recommended else 0.0

    why = [
        f"Estimated cubeless equity for side on roll: {cubeless_equity:+.3f}.",
        engine_note,
    ]
    if features["own_pips"] < features["opp_pips"]:
        why.append("Race context favors the side on roll.")
    if features["shots"] > 1:
        why.append("Contact risk is high, which reduces doubling urgency.")

    return CubeDecisionResponse(
        recommended_action=recommended,
        quality=_quality(delta),
        delta=round(delta, 4),
        why=why,
    )
