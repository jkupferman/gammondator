from __future__ import annotations

from app.analysis import _evaluate
from app.movegen import PositionState
from app.schemas import CubeDecisionRequest, CubeDecisionResponse


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


def evaluate_cube_decision(request: CubeDecisionRequest) -> CubeDecisionResponse:
    state = PositionState.from_position(request.position)
    cubeless_equity, features = _evaluate(state, request.position.turn)

    recommended, edge = _recommend_action(cubeless_equity, request.action)
    delta = abs(edge) if request.action != recommended else 0.0

    why = [
        f"Estimated cubeless equity for side on roll: {cubeless_equity:+.3f}.",
        "MVP cube thresholds are heuristic and should be replaced by engine-backed cube analysis.",
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
