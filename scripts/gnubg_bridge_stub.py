#!/usr/bin/env python3
"""
Stub bridge for GAMMONDATOR_GNUBG_BRIDGE_CMD development.

This script intentionally does NOT invoke GNU Backgammon. It mirrors the bridge
contract and uses Gammondator's heuristic evaluator so you can test backend
wiring end-to-end before wiring a real gnubg process.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_repo_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def main() -> int:
    _ensure_repo_on_path()
    from app.analysis import _apply_move, _evaluate
    from app.schemas import AnalyzeMoveRequest

    raw = sys.stdin.read()
    payload = AnalyzeMoveRequest.model_validate_json(raw)

    equities: dict[str, float] = {}
    win_pcts: dict[str, float] = {}
    for move in payload.candidate_moves:
        state = _apply_move(payload.position, move)
        equity, _ = _evaluate(state, payload.position.turn)
        equities[move.notation] = equity
        win_pcts[move.notation] = max(0.0, min(100.0, round(50.0 + (equity * 50.0), 3)))

    result = {
        "equities": equities,
        "win_pcts": win_pcts,
        "reasons": {
            notation: ["Stub bridge response. Replace with GNU Backgammon output."]
            for notation in equities
        },
    }
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
