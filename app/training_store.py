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


def _classify_leak_category(why_messages: list[str]) -> str:
    text = " ".join(message.lower() for message in why_messages)
    if "shot" in text or "blot" in text or "safer play" in text:
        return "safety"
    if "prime" in text or "containment" in text:
        return "prime_structure"
    if "race" in text or "pip" in text:
        return "race_timing"
    if "anchor" in text:
        return "anchors"
    return "general"


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
                    leak_category TEXT NOT NULL DEFAULT 'general',
                    position_json TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(move_reviews)")}
            if "leak_category" not in columns:
                conn.execute(
                    "ALTER TABLE move_reviews ADD COLUMN leak_category TEXT NOT NULL DEFAULT 'general'"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drill_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    review_id INTEGER NOT NULL,
                    chosen_notation TEXT NOT NULL,
                    expected_notation TEXT NOT NULL,
                    correct INTEGER NOT NULL,
                    FOREIGN KEY(review_id) REFERENCES move_reviews(id)
                )
                """
            )
            conn.commit()

    def record_review(self, position: Position, analysis: AnalyzeMoveResponse) -> int:
        now = datetime.now(tz=timezone.utc).isoformat()
        leak_category = _classify_leak_category(analysis.played_move.why)
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
                    leak_category,
                    position_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    leak_category,
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
                    quality,
                    leak_category
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
                    "leak_category": str(row["leak_category"]),
                }
                for row in rows
            ]

    def leak_summary(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    leak_category,
                    COUNT(*) AS move_count,
                    ROUND(AVG(equity_loss), 4) AS average_equity_loss,
                    MAX(equity_loss) AS max_equity_loss
                FROM move_reviews
                GROUP BY leak_category
                ORDER BY average_equity_loss DESC, move_count DESC
                """
            ).fetchall()

            return [
                {
                    "leak_category": str(row["leak_category"]),
                    "move_count": int(row["move_count"]),
                    "average_equity_loss": float(row["average_equity_loss"] or 0.0),
                    "max_equity_loss": float(row["max_equity_loss"] or 0.0),
                }
                for row in rows
            ]

    def drill_candidates(self, limit: int = 10, leak_category: str | None = None) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 50))
        with self._connect() as conn:
            if leak_category:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        leak_category,
                        equity_loss,
                        played_notation,
                        best_notation,
                        position_json
                    FROM move_reviews
                    WHERE leak_category = ?
                    ORDER BY equity_loss DESC, created_at DESC
                    LIMIT ?
                    """,
                    (leak_category, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        leak_category,
                        equity_loss,
                        played_notation,
                        best_notation,
                        position_json
                    FROM move_reviews
                    ORDER BY equity_loss DESC, created_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()

        drills: list[dict[str, object]] = []
        for row in rows:
            drills.append(
                {
                    "review_id": int(row["id"]),
                    "leak_category": str(row["leak_category"]),
                    "equity_loss": float(row["equity_loss"]),
                    "played_notation": str(row["played_notation"]),
                    "best_notation": str(row["best_notation"]),
                    "position": Position.model_validate_json(str(row["position_json"])),
                }
            )
        return drills

    def record_drill_attempt(self, review_id: int, chosen_notation: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT best_notation FROM move_reviews WHERE id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"review {review_id} not found")

            expected_notation = str(row["best_notation"])
            correct = int(chosen_notation.strip() == expected_notation)
            now = datetime.now(tz=timezone.utc).isoformat()

            cursor = conn.execute(
                """
                INSERT INTO drill_attempts (
                    created_at,
                    review_id,
                    chosen_notation,
                    expected_notation,
                    correct
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (now, review_id, chosen_notation.strip(), expected_notation, correct),
            )
            conn.commit()
            attempt_id = int(cursor.lastrowid)

        return {
            "attempt_id": attempt_id,
            "review_id": review_id,
            "correct": bool(correct),
            "expected_notation": expected_notation,
        }

    def drill_summary(self) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_attempts,
                    COALESCE(SUM(correct), 0) AS correct_attempts
                FROM drill_attempts
                """
            ).fetchone()

        total = int(row["total_attempts"] or 0)
        correct = int(row["correct_attempts"] or 0)
        accuracy = round((correct / total) if total else 0.0, 4)
        return {
            "total_attempts": total,
            "correct_attempts": correct,
            "accuracy": accuracy,
        }
