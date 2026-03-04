from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db import Database
from app.schemas import AnalyzeMoveResponse, Move, Position


class SessionStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.db = Database(db_path)
        self._init_schema()

    def _connect(self):
        return self.db.connect()

    @staticmethod
    def _extract_column_name(row) -> str:
        if isinstance(row, dict):
            return str(row.get("column_name", ""))
        return str(row[1])

    def _table_columns(self, conn, table_name: str) -> set[str]:
        if conn.is_postgres:
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                """,
                (table_name,),
            ).fetchall()
            return {str(row["column_name"]) for row in rows}
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {self._extract_column_name(row) for row in rows}

    def _init_schema(self) -> None:
        with self._connect() as conn:
            if conn.is_postgres:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        profile_id TEXT NOT NULL DEFAULT 'default',
                        status TEXT NOT NULL,
                        move_count INTEGER NOT NULL DEFAULT 0,
                        current_position_json TEXT NOT NULL
                    )
                    """
                )
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        profile_id TEXT NOT NULL DEFAULT 'default',
                        status TEXT NOT NULL,
                        move_count INTEGER NOT NULL DEFAULT 0,
                        current_position_json TEXT NOT NULL
                    )
                    """
                )
            columns = self._table_columns(conn, "sessions")
            if "profile_id" not in columns:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default'"
                )
            if conn.is_postgres:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_turns (
                        id BIGSERIAL PRIMARY KEY,
                        session_id BIGINT NOT NULL,
                        created_at TEXT NOT NULL,
                        turn TEXT NOT NULL,
                        actor TEXT NOT NULL DEFAULT 'human',
                        dice_json TEXT,
                        previous_position_json TEXT,
                        played_move_json TEXT,
                        played_notation TEXT NOT NULL,
                        quality TEXT NOT NULL,
                        equity_loss REAL NOT NULL,
                        analysis_json TEXT NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES sessions(id)
                    )
                    """
                )
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        turn TEXT NOT NULL,
                        actor TEXT NOT NULL DEFAULT 'human',
                        dice_json TEXT,
                        previous_position_json TEXT,
                        played_move_json TEXT,
                        played_notation TEXT NOT NULL,
                        quality TEXT NOT NULL,
                        equity_loss REAL NOT NULL,
                        analysis_json TEXT NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES sessions(id)
                    )
                    """
                )
            turn_columns = self._table_columns(conn, "session_turns")
            if "actor" not in turn_columns:
                conn.execute(
                    "ALTER TABLE session_turns ADD COLUMN actor TEXT NOT NULL DEFAULT 'human'"
                )
            if "dice_json" not in turn_columns:
                conn.execute("ALTER TABLE session_turns ADD COLUMN dice_json TEXT")
            if "previous_position_json" not in turn_columns:
                conn.execute("ALTER TABLE session_turns ADD COLUMN previous_position_json TEXT")
            if "played_move_json" not in turn_columns:
                conn.execute("ALTER TABLE session_turns ADD COLUMN played_move_json TEXT")

    def create_session(self, initial_position: Position, profile_id: str = "default") -> dict[str, object]:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            if conn.is_postgres:
                cursor = conn.execute(
                    """
                    INSERT INTO sessions (
                        created_at,
                        updated_at,
                        profile_id,
                        status,
                        move_count,
                        current_position_json
                    )
                    VALUES (?, ?, ?, 'active', 0, ?)
                    RETURNING id
                    """,
                    (now, now, profile_id, json.dumps(initial_position.model_dump())),
                )
                session_id = int(cursor.fetchone()["id"])
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO sessions (
                        created_at,
                        updated_at,
                        profile_id,
                        status,
                        move_count,
                        current_position_json
                    )
                    VALUES (?, ?, ?, 'active', 0, ?)
                    """,
                    (now, now, profile_id, json.dumps(initial_position.model_dump())),
                )
                session_id = int(cursor.lastrowid)

        return {
            "session_id": session_id,
            "profile_id": profile_id,
            "status": "active",
            "move_count": 0,
            "current_position": initial_position,
        }

    def list_sessions(self, profile_id: str = "default", status: str | None = None) -> list[dict[str, object]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT id, profile_id, status, move_count, current_position_json
                    FROM sessions
                    WHERE profile_id = ? AND status = ?
                    ORDER BY updated_at DESC
                    """,
                    (profile_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, profile_id, status, move_count, current_position_json
                    FROM sessions
                    WHERE profile_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (profile_id,),
                ).fetchall()

        return [
            {
                "session_id": int(row["id"]),
                "profile_id": str(row["profile_id"]),
                "status": str(row["status"]),
                "move_count": int(row["move_count"]),
                "current_position": Position.model_validate_json(str(row["current_position_json"])),
            }
            for row in rows
        ]

    def get_session(self, session_id: int) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, profile_id, status, move_count, current_position_json
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "session_id": int(row["id"]),
            "profile_id": str(row["profile_id"]),
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
        played_move: Move,
        actor: str = "human",
    ) -> dict[str, object]:
        now = datetime.now(tz=timezone.utc).isoformat()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT move_count, status FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"session {session_id} not found")
            if str(row["status"]) != "active":
                raise ValueError(f"session {session_id} is not active")

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
                    actor,
                    dice_json,
                    previous_position_json,
                    played_move_json,
                    played_notation,
                    quality,
                    equity_loss,
                    analysis_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now,
                    previous_position.turn,
                    actor,
                    json.dumps([int(previous_position.dice[0]), int(previous_position.dice[1])]),
                    previous_position.model_dump_json(),
                    played_move.model_dump_json(),
                    analysis.played_move.notation,
                    analysis.played_move.quality,
                    float(analysis.played_move.delta_vs_best),
                    analysis.model_dump_json(),
                ),
            )

        return {
            "session_id": session_id,
            "move_count": next_move_count,
            "current_position": new_position,
        }

    def list_turns(
        self,
        session_id: int,
        limit: int = 200,
        actor: str | None = None,
    ) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 500))
        actor_filter = actor if actor in {"human", "ai"} else None
        with self._connect() as conn:
            session = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if session is None:
                raise ValueError(f"session {session_id} not found")
            if actor_filter:
                rows = conn.execute(
                    """
                    SELECT id, created_at, turn, actor, dice_json, played_notation, quality, equity_loss, analysis_json
                    FROM session_turns
                    WHERE session_id = ? AND actor = ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (session_id, actor_filter, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, created_at, turn, actor, dice_json, played_notation, quality, equity_loss, analysis_json
                    FROM session_turns
                    WHERE session_id = ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (session_id, safe_limit),
                ).fetchall()

        turns: list[dict[str, object]] = []
        for row in rows:
            analysis_payload = json.loads(str(row["analysis_json"]))
            played_move = analysis_payload.get("played_move", {})
            best_move = analysis_payload.get("best_move", {})
            raw_dice = row["dice_json"]
            dice: tuple[int, int] | None = None
            if raw_dice:
                try:
                    decoded = json.loads(str(raw_dice))
                    if isinstance(decoded, list) and len(decoded) == 2:
                        dice = (int(decoded[0]), int(decoded[1]))
                except (json.JSONDecodeError, TypeError, ValueError):
                    dice = None
            turns.append(
                {
                    "turn_id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "turn": str(row["turn"]),
                    "actor": str(row["actor"]),
                    "dice": dice,
                    "played_notation": str(row["played_notation"]),
                    "quality": str(row["quality"]),
                    "equity_loss": float(row["equity_loss"]),
                    "best_notation": str(best_move.get("notation", "")),
                    "why": list(played_move.get("why", [])),
                }
            )
        return turns

    def get_turn_replay(self, session_id: int, turn_id: int) -> dict[str, object]:
        with self._connect() as conn:
            session = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if session is None:
                raise ValueError(f"session {session_id} not found")
            row = conn.execute(
                """
                SELECT id, previous_position_json, played_move_json
                FROM session_turns
                WHERE session_id = ? AND id = ?
                """,
                (session_id, turn_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"turn {turn_id} not found for session {session_id}")
            if not row["previous_position_json"] or not row["played_move_json"]:
                raise ValueError(f"turn {turn_id} replay data unavailable")

        return {
            "session_id": session_id,
            "turn_id": int(row["id"]),
            "previous_position": Position.model_validate_json(str(row["previous_position_json"])),
            "played_move": Move.model_validate_json(str(row["played_move_json"])),
        }

    def set_position(self, session_id: int, position: Position) -> dict[str, object]:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, status, move_count FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"session {session_id} not found")
            if str(row["status"]) != "active":
                raise ValueError(f"session {session_id} is not active")

            conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?, current_position_json = ?
                WHERE id = ?
                """,
                (now, json.dumps(position.model_dump()), session_id),
            )

        return {
            "session_id": int(row["id"]),
            "move_count": int(row["move_count"]),
            "current_position": position,
        }

    def close_session(self, session_id: int) -> dict[str, object]:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"session {session_id} not found")

            conn.execute(
                "UPDATE sessions SET status = 'completed', updated_at = ? WHERE id = ?",
                (now, session_id),
            )

        return {"session_id": int(row["id"]), "status": "completed"}

    def session_report(self, session_id: int, top_n: int = 5) -> dict[str, object]:
        safe_limit = max(1, min(top_n, 20))
        with self._connect() as conn:
            session = conn.execute(
                """
                SELECT id, status, move_count, created_at, updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                raise ValueError(f"session {session_id} not found")

            summary = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_turns,
                    COALESCE(AVG(equity_loss), 0.0) AS avg_equity_loss,
                    SUM(CASE WHEN quality = 'inaccuracy' THEN 1 ELSE 0 END) AS inaccuracies,
                    SUM(CASE WHEN quality = 'mistake' THEN 1 ELSE 0 END) AS mistakes,
                    SUM(CASE WHEN quality = 'blunder' THEN 1 ELSE 0 END) AS blunders
                FROM session_turns
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

            turns = conn.execute(
                """
                SELECT id, created_at, turn, played_notation, quality, equity_loss, analysis_json
                FROM session_turns
                WHERE session_id = ?
                ORDER BY equity_loss DESC, created_at DESC
                LIMIT ?
                """,
                (session_id, safe_limit),
            ).fetchall()

        top_mistakes: list[dict[str, object]] = []
        for row in turns:
            analysis_payload = json.loads(str(row["analysis_json"]))
            played_move = analysis_payload.get("played_move", {})
            best_move = analysis_payload.get("best_move", {})
            top_mistakes.append(
                {
                    "turn_id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "turn": str(row["turn"]),
                    "quality": str(row["quality"]),
                    "equity_loss": float(row["equity_loss"]),
                    "played_notation": str(row["played_notation"]),
                    "best_notation": str(best_move.get("notation", "")),
                    "why": list(played_move.get("why", [])),
                }
            )

        return {
            "session_id": int(session["id"]),
            "status": str(session["status"]),
            "move_count": int(session["move_count"]),
            "created_at": str(session["created_at"]),
            "updated_at": str(session["updated_at"]),
            "total_turns": int(summary["total_turns"] or 0),
            "average_equity_loss": round(float(summary["avg_equity_loss"] or 0.0), 4),
            "inaccuracies": int(summary["inaccuracies"] or 0),
            "mistakes": int(summary["mistakes"] or 0),
            "blunders": int(summary["blunders"] or 0),
            "top_mistakes": top_mistakes,
        }
