#!/usr/bin/env python3
"""
Real GNU Backgammon bridge.

Input: AnalyzeMoveRequest JSON from stdin
Output: {"equities": {...}, "reasons": {...}} JSON to stdout

This bridge evaluates each candidate move by:
1) applying move to the input position,
2) setting resulting board in GNUbg using `set board simple`,
3) running `eval`,
4) parsing `2-ply cubeless equity`.

Equity is converted to the perspective of the mover in the input request.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from app.analysis import _apply_move
from app.schemas import AnalyzeMoveRequest

EQUITY_PATTERN = re.compile(r"2-ply cubeless equity\s+([+-]?\d+(?:\.\d+)?)")


def _state_to_simple_board_numbers(state) -> list[int]:
    # GNUbg `set board simple` accepts: [bar_x, p1..p24, bar_o].
    # Our model maps positive checkers to white (x) and negative to black (o).
    return [state.bar_white, *state.points, state.bar_black]


def _eval_position_with_gnubg(simple_numbers: list[int]) -> float:
    gnubg_bin = os.getenv("GNUBG_BIN", "/opt/local/bin/gnubg")
    board_args = " ".join(str(value) for value in simple_numbers)
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
        raise RuntimeError(proc.stderr.strip() or "gnubg evaluation failed")

    match = EQUITY_PATTERN.search(proc.stdout)
    if not match:
        raise RuntimeError("failed to parse equity from gnubg output")

    return float(match.group(1))


def main() -> int:
    request = AnalyzeMoveRequest.model_validate_json(sys.stdin.read())

    equities: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for move in request.candidate_moves:
        next_state = _apply_move(request.position, move)
        simple_numbers = _state_to_simple_board_numbers(next_state)
        white_equity = _eval_position_with_gnubg(simple_numbers)

        mover_equity = white_equity if request.position.turn == "white" else -white_equity
        equities[move.notation] = round(mover_equity, 4)
        reasons[move.notation] = [
            f"GNUbg 2-ply cubeless equity: {mover_equity:+.4f}",
            "Evaluated after applying this candidate move.",
        ]

    sys.stdout.write(json.dumps({"equities": equities, "reasons": reasons}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
