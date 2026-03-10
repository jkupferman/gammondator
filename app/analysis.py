from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from app.schemas import (
    AnalyzeMoveRequest,
    AnalyzeMoveResponse,
    ChooseAIMoveRequest,
    ChooseAIMoveResponse,
    Move,
    MoveScore,
    Position,
    Side,
)


@dataclass
class PositionState:
    points: list[int]
    bar_white: int
    bar_black: int
    off_white: int
    off_black: int

    @classmethod
    def from_position(cls, position: Position) -> PositionState:
        return cls(
            points=position.points.copy(),
            bar_white=position.bar_white,
            bar_black=position.bar_black,
            off_white=position.off_white,
            off_black=position.off_black,
        )


def _pip_count(state: PositionState, side: Side) -> int:
    total = 0
    for idx, value in enumerate(state.points):
        point = idx + 1
        if side == "white" and value > 0:
            total += value * point
        if side == "black" and value < 0:
            total += (-value) * (25 - point)

    if side == "white":
        total += state.bar_white * 25
    else:
        total += state.bar_black * 25

    return total


def _blots(state: PositionState, side: Side) -> int:
    target = 1 if side == "white" else -1
    return sum(1 for value in state.points if value == target)


def _anchors(state: PositionState, side: Side) -> int:
    # Anchor count in opponent home board.
    if side == "white":
        home_points = range(18, 24)
        return sum(1 for i in home_points if state.points[i] >= 2)

    home_points = range(0, 6)
    return sum(1 for i in home_points if state.points[i] <= -2)


def _longest_prime(state: PositionState, side: Side) -> int:
    longest = 0
    streak = 0
    for value in state.points:
        own_made = value >= 2 if side == "white" else value <= -2
        if own_made:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    return longest


def _direct_shots_allowed(state: PositionState, side: Side) -> int:
    shots = 0
    for idx, value in enumerate(state.points):
        point = idx + 1
        is_blot = value == 1 if side == "white" else value == -1
        if not is_blot:
            continue

        blot_is_shot = False
        for die in range(1, 7):
            if side == "white":
                attacker_point = point - die
                if attacker_point < 1:
                    continue
                attacker_value = state.points[attacker_point - 1]
                if attacker_value < 0:
                    blot_is_shot = True
            else:
                attacker_point = point + die
                if attacker_point > 24:
                    continue
                attacker_value = state.points[attacker_point - 1]
                if attacker_value > 0:
                    blot_is_shot = True

            if blot_is_shot:
                shots += 1
                break

    return shots


def _evaluate(state: PositionState, side: Side) -> tuple[float, dict[str, int]]:
    opponent = "black" if side == "white" else "white"
    own_pips = _pip_count(state, side)
    opp_pips = _pip_count(state, opponent)
    blots = _blots(state, side)
    anchors = _anchors(state, side)
    prime = _longest_prime(state, side)
    shots = _direct_shots_allowed(state, side)
    off = state.off_white if side == "white" else state.off_black

    equity = (
        (opp_pips - own_pips) * 0.02
        + anchors * 0.03
        + prime * 0.08
        + off * 0.10
        - blots * 0.12
        - shots * 0.07
    )

    return round(equity, 4), {
        "own_pips": own_pips,
        "opp_pips": opp_pips,
        "blots": blots,
        "anchors": anchors,
        "prime": prime,
        "shots": shots,
        "off": off,
    }


def _apply_move(position: Position, move: Move) -> PositionState:
    side = position.turn
    state = PositionState.from_position(position)

    for step in move.steps:
        from_point = step.from_point
        to_point = step.to_point

        if side == "white":
            if from_point == 25:
                if state.bar_white <= 0:
                    raise ValueError("white checker not present on bar")
                state.bar_white -= 1
            else:
                if from_point < 1 or from_point > 24:
                    raise ValueError(f"invalid from_point for white: {from_point}")
                if state.points[from_point - 1] <= 0:
                    raise ValueError(f"white checker not present at point {from_point}")

                state.points[from_point - 1] -= 1

            if to_point == 0:
                state.off_white += 1
                continue
            if to_point < 1 or to_point > 24:
                raise ValueError(f"invalid to_point for white: {to_point}")

            destination = state.points[to_point - 1]
            if destination == -1:
                state.points[to_point - 1] = 1
                state.bar_black += 1
            elif destination <= -2:
                raise ValueError(f"white cannot move to blocked point {to_point}")
            else:
                state.points[to_point - 1] += 1

        else:
            if from_point == 0:
                if state.bar_black <= 0:
                    raise ValueError("black checker not present on bar")
                state.bar_black -= 1
            else:
                if from_point < 1 or from_point > 24:
                    raise ValueError(f"invalid from_point for black: {from_point}")
                if state.points[from_point - 1] >= 0:
                    raise ValueError(f"black checker not present at point {from_point}")

                state.points[from_point - 1] += 1

            if to_point == 25:
                state.off_black += 1
                continue
            if to_point < 1 or to_point > 24:
                raise ValueError(f"invalid to_point for black: {to_point}")

            destination = state.points[to_point - 1]
            if destination == 1:
                state.points[to_point - 1] = -1
                state.bar_white += 1
            elif destination >= 2:
                raise ValueError(f"black cannot move to blocked point {to_point}")
            else:
                state.points[to_point - 1] -= 1

    return state


def quality_from_delta(delta_vs_best: float) -> str:
    if delta_vs_best <= 0.005:
        return "excellent"
    if delta_vs_best <= 0.020:
        return "good"
    if delta_vs_best <= 0.050:
        return "inaccuracy"
    if delta_vs_best <= 0.100:
        return "mistake"
    return "blunder"


def _why_from_features(feature_delta: dict[str, int], is_best: bool) -> list[str]:
    messages: list[str] = []

    if feature_delta["shots"] < 0:
        messages.append(f"Safer play: exposed direct shots reduced by {abs(feature_delta['shots'])}.")
    elif feature_delta["shots"] > 0:
        messages.append(f"Risk increased: exposed direct shots increased by {feature_delta['shots']}.")

    if feature_delta["blots"] < 0:
        messages.append(f"Cleaner structure: blots reduced by {abs(feature_delta['blots'])}.")
    elif feature_delta["blots"] > 0:
        messages.append(f"Loose structure: created {feature_delta['blots']} additional blot(s).")

    if feature_delta["prime"] > 0:
        messages.append(f"Containment improved: prime length increased by {feature_delta['prime']}.")

    pip_delta = feature_delta["own_pips"]
    if pip_delta < 0:
        messages.append(f"Race improved: pip count reduced by {abs(pip_delta)}.")
    elif pip_delta > 0:
        messages.append(f"Race slowed: pip count increased by {pip_delta}.")

    if not messages and is_best:
        messages.append("Best practical equity among candidate moves.")
    elif not messages:
        messages.append("This play is close in equity but lacks a major structural gain.")

    return messages


def analyze_with_explicit_equities(
    request: AnalyzeMoveRequest,
    move_equities: dict[str, float],
    move_reasons: dict[str, list[str]] | None = None,
    move_win_pcts: dict[str, float] | None = None,
) -> AnalyzeMoveResponse:
    baseline_state = PositionState.from_position(request.position)
    _, baseline_features = _evaluate(baseline_state, request.position.turn)

    scored_moves: list[tuple[Move, float, dict[str, int]]] = []
    for move in request.candidate_moves:
        if move.notation not in move_equities:
            raise ValueError(f"missing equity for move: {move.notation}")

        state = _apply_move(request.position, move)
        _, features = _evaluate(state, request.position.turn)
        scored_moves.append((move, move_equities[move.notation], features))

    scored_moves.sort(key=lambda item: item[1], reverse=True)
    best_move, best_equity, best_features = scored_moves[0]

    reasons = move_reasons or {}
    win_pcts = move_win_pcts or {}

    def to_score(item: tuple[Move, float, dict[str, int]]) -> MoveScore:
        move, equity, features = item
        delta = round(best_equity - equity, 4)
        feature_delta = {key: features[key] - baseline_features[key] for key in features}
        default_why = _why_from_features(feature_delta, is_best=isclose(delta, 0.0, abs_tol=1e-9))
        move_win_pct = win_pcts.get(move.notation)
        return MoveScore(
            notation=move.notation,
            equity=round(equity, 4),
            win_pct=round(float(move_win_pct), 6) if move_win_pct is not None else None,
            delta_vs_best=delta,
            quality=quality_from_delta(delta),
            why=reasons.get(move.notation, default_why),
        )

    top_moves = [to_score(item) for item in scored_moves[:3]]

    played = next(
        (item for item in scored_moves if item[0].notation == request.played_move.notation),
        None,
    )
    if played is None:
        played_state = _apply_move(request.position, request.played_move)
        played_equity = move_equities.get(request.played_move.notation)
        if played_equity is None:
            played_equity, _ = _evaluate(played_state, request.position.turn)
        _, played_features = _evaluate(played_state, request.position.turn)
        played = (request.played_move, played_equity, played_features)

    return AnalyzeMoveResponse(
        best_move=to_score((best_move, best_equity, best_features)),
        played_move=to_score(played),
        top_moves=top_moves,
    )


def analyze_move(request: AnalyzeMoveRequest) -> AnalyzeMoveResponse:
    move_equities: dict[str, float] = {}
    for move in request.candidate_moves:
        state = _apply_move(request.position, move)
        equity, _ = _evaluate(state, request.position.turn)
        move_equities[move.notation] = equity

    if request.played_move.notation not in move_equities:
        played_state = _apply_move(request.position, request.played_move)
        move_equities[request.played_move.notation], _ = _evaluate(played_state, request.position.turn)

    return analyze_with_explicit_equities(request, move_equities)


def choose_ai_move(request: ChooseAIMoveRequest) -> ChooseAIMoveResponse:
    pseudo_request = AnalyzeMoveRequest(
        position=request.position,
        played_move=request.candidate_moves[0],
        candidate_moves=request.candidate_moves,
    )
    analyzed = analyze_move(pseudo_request)
    return ChooseAIMoveResponse(selected_move=analyzed.best_move, top_moves=analyzed.top_moves)


def apply_move_to_position(
    position: Position,
    move: Move,
    next_dice: tuple[int, int],
    next_turn: Side | None = None,
) -> Position:
    state = _apply_move(position, move)
    resulting_turn = next_turn or ("black" if position.turn == "white" else "white")
    return Position(
        points=state.points,
        bar_white=state.bar_white,
        bar_black=state.bar_black,
        off_white=state.off_white,
        off_black=state.off_black,
        turn=resulting_turn,
        cube_value=position.cube_value,
        dice=next_dice,
    )
