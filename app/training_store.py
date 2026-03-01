from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import AnalyzeMoveResponse, Position


@dataclass
class TrainingSummary:
    total_moves: int
    average_equity_loss: float
    inaccuracies: int
    mistakes: int
    blunders: int
    last_recorded_at: str | None


class TrainingStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS move_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    turn TEXT NOT NULL,
                    dice_1 INTEGER NOT NULL,
                    dice_2 INTEGER NOT NULL,
                    played_notation TEXT NOT NULL,
                    best_notation TEXT NOT NULL,
                    played_equity REAL NOT NULL,
                    best_equity REAL NOT NULL,
                    equity_loss REAL NOT NULL,
                    quality TEXT NOT NULL,
                    position_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def record_review(self, position: Position, analysis: AnalyzeMoveResponse) -> int:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO move_reviews (
                    created_at,
                    turn,
                    dice_1,
                    dice_2,
                    played_notation,
                    best_notation,
                    played_equity,
                    best_equity,
                    equity_loss,
                    quality,
                    position_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    position.turn,
                    int(position.dice[0]),
                    int(position.dice[1]),
                    analysis.played_move.notation,
                    analysis.best_move.notation,
                    float(analysis.played_move.equity),
                    float(analysis.best_move.equity),
                    float(analysis.played_move.delta_vs_best),
                    analysis.played_move.quality,
                    json.dumps(position.model_dump()),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def summary(self) -> TrainingSummary:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_moves,
                    COALESCE(AVG(equity_loss), 0.0) AS average_equity_loss,
                    SUM(CASE WHEN quality = 'inaccuracy' THEN 1 ELSE 0 END) AS inaccuracies,
                    SUM(CASE WHEN quality = 'mistake' THEN 1 ELSE 0 END) AS mistakes,
                    SUM(CASE WHEN quality = 'blunder' THEN 1 ELSE 0 END) AS blunders,
                    MAX(created_at) AS last_recorded_at
                FROM move_reviews
                """
            ).fetchone()

            return TrainingSummary(
                total_moves=int(row["total_moves"] or 0),
                average_equity_loss=round(float(row["average_equity_loss"] or 0.0), 4),
                inaccuracies=int(row["inaccuracies"] or 0),
                mistakes=int(row["mistakes"] or 0),
                blunders=int(row["blunders"] or 0),
                last_recorded_at=row["last_recorded_at"],
            )

    def top_mistakes(self, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    created_at,
                    turn,
                    dice_1,
                    dice_2,
                    played_notation,
                    best_notation,
                    played_equity,
                    best_equity,
                    equity_loss,
                    quality
                FROM move_reviews
                ORDER BY equity_loss DESC, created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

            return [
                {
                    "id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "turn": str(row["turn"]),
                    "dice": [int(row["dice_1"]), int(row["dice_2"])],
                    "played_notation": str(row["played_notation"]),
                    "best_notation": str(row["best_notation"]),
                    "played_equity": float(row["played_equity"]),
                    "best_equity": float(row["best_equity"]),
                    "equity_loss": float(row["equity_loss"]),
                    "quality": str(row["quality"]),
                }
                for row in rows
            ]
