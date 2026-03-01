#!/usr/bin/env python3
"""
Real GNU Backgammon bridge.

Input: AnalyzeMoveRequest JSON from stdin
Output: {"equities": {...}, "reasons": {...}} JSON to stdout

This bridge evaluates each candidate move by:
1) applying move to the input position,
2) setting resulting board in GNUbg using `set board simple`,
3) running `eval`,
4) parsing cubeless equity (0-ply/1-ply/2-ply).

Equity is converted to the perspective of the mover in the input request.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys

from app.analysis import _apply_move
from app.schemas import AnalyzeMoveRequest

PATTERN_BY_MODE = {
    "0ply": re.compile(r"0-ply cubeless equity\s+([+-]?\d+(?:\.\d+)?)"),
    "1ply": re.compile(r"1-ply cubeless equity\s+([+-]?\d+(?:\.\d+)?)"),
    "2ply": re.compile(r"2-ply cubeless equity\s+([+-]?\d+(?:\.\d+)?)"),
}


def _cache_init(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gnubg_equity_cache (
                board_key TEXT NOT NULL,
                mode TEXT NOT NULL,
                equity REAL NOT NULL,
                PRIMARY KEY (board_key, mode)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _cache_get(db_path: str, board_key: str, mode: str) -> float | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT equity FROM gnubg_equity_cache WHERE board_key = ? AND mode = ?",
            (board_key, mode),
        ).fetchone()
        if row is None:
            return None
        return float(row[0])
    finally:
        conn.close()


def _cache_set(db_path: str, board_key: str, mode: str, equity: float) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO gnubg_equity_cache (board_key, mode, equity)
            VALUES (?, ?, ?)
            ON CONFLICT(board_key, mode) DO UPDATE SET equity = excluded.equity
            """,
            (board_key, mode, equity),
        )
        conn.commit()
    finally:
        conn.close()


def _state_to_simple_board_numbers(state) -> list[int]:
    # GNUbg `set board simple` accepts: [bar_x, p1..p24, bar_o].
    # Our model maps positive checkers to white (x) and negative to black (o).
    return [state.bar_white, *state.points, state.bar_black]


def _eval_position_with_gnubg(simple_numbers: list[int], mode: str, timeout_seconds: float) -> float:
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
        timeout=timeout_seconds,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gnubg evaluation failed")

    pattern = PATTERN_BY_MODE.get(mode, PATTERN_BY_MODE["2ply"])
    match = pattern.search(proc.stdout)
    if not match and mode != "2ply":
        # Fallback parse if requested depth line is unavailable.
        match = PATTERN_BY_MODE["2ply"].search(proc.stdout)
    if not match:
        raise RuntimeError("failed to parse equity from gnubg output")

    return float(match.group(1))


def main() -> int:
    request = AnalyzeMoveRequest.model_validate_json(sys.stdin.read())

    eval_mode = os.getenv("GAMMONDATOR_GNUBG_EVAL_MODE", "2ply").strip().lower()
    timeout_seconds = float(os.getenv("GAMMONDATOR_GNUBG_TIMEOUT", "15"))
    cache_enabled = os.getenv("GAMMONDATOR_GNUBG_CACHE", "1") != "0"
    cache_path = os.getenv("GAMMONDATOR_GNUBG_CACHE_DB", "gammondator_gnubg_cache.db")
    if cache_enabled:
        _cache_init(cache_path)

    equities: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for move in request.candidate_moves:
        next_state = _apply_move(request.position, move)
        simple_numbers = _state_to_simple_board_numbers(next_state)
        board_key = ",".join(str(value) for value in simple_numbers)

        cached = _cache_get(cache_path, board_key, eval_mode) if cache_enabled else None
        if cached is not None:
            white_equity = cached
            cache_note = "cache hit"
        else:
            white_equity = _eval_position_with_gnubg(simple_numbers, eval_mode, timeout_seconds)
            if cache_enabled:
                _cache_set(cache_path, board_key, eval_mode, white_equity)
            cache_note = "fresh eval"

        mover_equity = white_equity if request.position.turn == "white" else -white_equity
        equities[move.notation] = round(mover_equity, 4)
        reasons[move.notation] = [
            f"GNUbg {eval_mode} cubeless equity: {mover_equity:+.4f} ({cache_note})",
            "Evaluated after applying this candidate move to the supplied position.",
        ]

    sys.stdout.write(json.dumps({"equities": equities, "reasons": reasons}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
