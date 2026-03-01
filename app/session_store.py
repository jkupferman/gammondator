from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import AnalyzeMoveResponse, Position


class SessionStore:
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
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    move_count INTEGER NOT NULL DEFAULT 0,
                    current_position_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    turn TEXT NOT NULL,
                    played_notation TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    equity_loss REAL NOT NULL,
                    analysis_json TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )
            conn.commit()

    def create_session(self, initial_position: Position) -> dict[str, object]:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sessions (created_at, updated_at, status, move_count, current_position_json)
                VALUES (?, ?, 'active', 0, ?)
                """,
                (now, now, json.dumps(initial_position.model_dump())),
            )
            conn.commit()
            session_id = int(cursor.lastrowid)

        return {
            "session_id": session_id,
            "status": "active",
            "move_count": 0,
            "current_position": initial_position,
        }

    def get_session(self, session_id: int) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, status, move_count, current_position_json
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "session_id": int(row["id"]),
            "status": str(row["status"]),
            "move_count": int(row["move_count"]),
            "current_position": Position.model_validate_json(str(row["current_position_json"])),
        }

    def apply_turn(
        self,
        session_id: int,
        previous_position: Position,
        new_position: Position,
        analysis: AnalyzeMoveResponse,
    ) -> dict[str, object]:
        now = datetime.now(tz=timezone.utc).isoformat()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT move_count FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"session {session_id} not found")

            next_move_count = int(row["move_count"]) + 1

            conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?, move_count = ?, current_position_json = ?
                WHERE id = ?
                """,
                (now, next_move_count, json.dumps(new_position.model_dump()), session_id),
            )

            conn.execute(
                """
                INSERT INTO session_turns (
                    session_id,
                    created_at,
                    turn,
                    played_notation,
                    quality,
                    equity_loss,
                    analysis_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now,
                    previous_position.turn,
                    analysis.played_move.notation,
                    analysis.played_move.quality,
                    float(analysis.played_move.delta_vs_best),
                    analysis.model_dump_json(),
                ),
            )
            conn.commit()

        return {
            "session_id": session_id,
            "move_count": next_move_count,
            "current_position": new_position,
        }
