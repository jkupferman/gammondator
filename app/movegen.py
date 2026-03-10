from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from app.schemas import Move, MoveStep, Position, Side


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


def _is_home_point(side: Side, point: int) -> bool:
    if side == "white":
        return 1 <= point <= 6
    return 19 <= point <= 24


def _all_in_home(state: PositionState, side: Side) -> bool:
    if side == "white":
        if state.bar_white > 0:
            return False
        return all(value <= 0 for value in state.points[6:])

    if state.bar_black > 0:
        return False
    return all(value >= 0 for value in state.points[:18])


def _is_open_point(state: PositionState, side: Side, point: int) -> bool:
    value = state.points[point - 1]
    if side == "white":
        return value >= -1
    return value <= 1


def _can_bear_off_overshoot(state: PositionState, side: Side, from_point: int) -> bool:
    if side == "white":
        # White bears off toward 0. Overshoot allowed only with no checkers on higher points.
        for point in range(from_point + 1, 7):
            if state.points[point - 1] > 0:
                return False
        return True

    # Black bears off toward 25. Overshoot allowed only with no checkers on lower points.
    for point in range(19, from_point):
        if state.points[point - 1] < 0:
            return False
    return True


def _apply_step(state: PositionState, side: Side, from_point: int, to_point: int) -> PositionState:
    next_state = PositionState(
        points=state.points.copy(),
        bar_white=state.bar_white,
        bar_black=state.bar_black,
        off_white=state.off_white,
        off_black=state.off_black,
    )

    if side == "white":
        if from_point == 25:
            if next_state.bar_white <= 0:
                raise ValueError("white checker not present on bar")
            next_state.bar_white -= 1
        else:
            if from_point < 1 or from_point > 24 or next_state.points[from_point - 1] <= 0:
                raise ValueError(f"white checker not present at point {from_point}")
            next_state.points[from_point - 1] -= 1

        if to_point == 0:
            next_state.off_white += 1
            return next_state

        destination = next_state.points[to_point - 1]
        if destination <= -2:
            raise ValueError(f"white cannot move to blocked point {to_point}")
        if destination == -1:
            next_state.points[to_point - 1] = 1
            next_state.bar_black += 1
        else:
            next_state.points[to_point - 1] += 1

        return next_state

    if from_point == 0:
        if next_state.bar_black <= 0:
            raise ValueError("black checker not present on bar")
        next_state.bar_black -= 1
    else:
        if from_point < 1 or from_point > 24 or next_state.points[from_point - 1] >= 0:
            raise ValueError(f"black checker not present at point {from_point}")
        next_state.points[from_point - 1] += 1

    if to_point == 25:
        next_state.off_black += 1
        return next_state

    destination = next_state.points[to_point - 1]
    if destination >= 2:
        raise ValueError(f"black cannot move to blocked point {to_point}")
    if destination == 1:
        next_state.points[to_point - 1] = -1
        next_state.bar_white += 1
    else:
        next_state.points[to_point - 1] -= 1

    return next_state


def _legal_steps_for_die(state: PositionState, side: Side, die: int) -> list[tuple[MoveStep, PositionState]]:
    steps: list[tuple[MoveStep, PositionState]] = []

    if side == "white" and state.bar_white > 0:
        to_point = 25 - die
        if _is_open_point(state, side, to_point):
            step = MoveStep(from_point=25, to_point=to_point)
            steps.append((step, _apply_step(state, side, step.from_point, step.to_point)))
        return steps

    if side == "black" and state.bar_black > 0:
        to_point = die
        if _is_open_point(state, side, to_point):
            step = MoveStep(from_point=0, to_point=to_point)
            steps.append((step, _apply_step(state, side, step.from_point, step.to_point)))
        return steps

    if side == "white":
        from_points = [point for point in range(24, 0, -1) if state.points[point - 1] > 0]
        for from_point in from_points:
            to_point = from_point - die
            if to_point >= 1:
                if not _is_open_point(state, side, to_point):
                    continue
                step = MoveStep(from_point=from_point, to_point=to_point)
                steps.append((step, _apply_step(state, side, step.from_point, step.to_point)))
                continue

            if not _is_home_point(side, from_point):
                continue
            if not _all_in_home(state, side):
                continue

            if to_point == 0 or _can_bear_off_overshoot(state, side, from_point):
                step = MoveStep(from_point=from_point, to_point=0)
                steps.append((step, _apply_step(state, side, step.from_point, step.to_point)))

        return steps

    from_points = [point for point in range(1, 25) if state.points[point - 1] < 0]
    for from_point in from_points:
        to_point = from_point + die
        if to_point <= 24:
            if not _is_open_point(state, side, to_point):
                continue
            step = MoveStep(from_point=from_point, to_point=to_point)
            steps.append((step, _apply_step(state, side, step.from_point, step.to_point)))
            continue

        if not _is_home_point(side, from_point):
            continue
        if not _all_in_home(state, side):
            continue

        if to_point == 25 or _can_bear_off_overshoot(state, side, from_point):
            step = MoveStep(from_point=from_point, to_point=25)
            steps.append((step, _apply_step(state, side, step.from_point, step.to_point)))

    return steps


def _step_to_notation(step: MoveStep) -> str:
    from_text = "bar" if step.from_point in (0, 25) else str(step.from_point)
    to_text = "off" if step.to_point in (0, 25) else str(step.to_point)
    return f"{from_text}/{to_text}"


def _sequence_to_move(steps: list[MoveStep]) -> Move:
    notation = " ".join(_step_to_notation(step) for step in steps)
    return Move(notation=notation, steps=steps)


def move_signature(move: Move) -> tuple[tuple[int, int], ...]:
    return tuple((step.from_point, step.to_point) for step in move.steps)


def legal_move_signatures(position: Position) -> set[tuple[tuple[int, int], ...]]:
    return {move_signature(move) for move in generate_legal_moves(position)}


def is_legal_move(position: Position, move: Move) -> bool:
    return move_signature(move) in legal_move_signatures(position)


def generate_legal_moves(position: Position) -> list[Move]:
    if position.dice[0] == position.dice[1]:
        orders = [tuple([position.dice[0]] * 4)]
    else:
        orders = list(permutations(position.dice, 2))

    results: list[tuple[list[MoveStep], list[int]]] = []

    def explore(
        state: PositionState,
        side: Side,
        dice_order: tuple[int, ...],
        index: int,
        steps: list[MoveStep],
        used_dice: list[int],
    ) -> None:
        if index >= len(dice_order):
            results.append((steps.copy(), used_dice.copy()))
            return

        die = dice_order[index]
        options = _legal_steps_for_die(state, side, die)
        if not options:
            results.append((steps.copy(), used_dice.copy()))
            return

        for step, next_state in options:
            steps.append(step)
            used_dice.append(die)
            explore(next_state, side, dice_order, index + 1, steps, used_dice)
            steps.pop()
            used_dice.pop()

    for order in orders:
        explore(
            state=PositionState.from_position(position),
            side=position.turn,
            dice_order=order,
            index=0,
            steps=[],
            used_dice=[],
        )

    if not results:
        return []

    max_steps_used = max(len(steps) for steps, _ in results)
    filtered = [(steps, dice_used) for steps, dice_used in results if len(steps) == max_steps_used]

    if position.dice[0] != position.dice[1] and max_steps_used == 1:
        higher_die = max(position.dice)
        higher_only = [(steps, dice_used) for steps, dice_used in filtered if dice_used and dice_used[0] == higher_die]
        if higher_only:
            filtered = higher_only

    unique: dict[tuple[tuple[int, int], ...], Move] = {}
    for steps, _ in filtered:
        if not steps:
            continue
        key = tuple((step.from_point, step.to_point) for step in steps)
        if key not in unique:
            unique[key] = _sequence_to_move(steps)

    return sorted(unique.values(), key=lambda move: move.notation)
