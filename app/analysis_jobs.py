from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import AnalysisJobCreateRequest


class AnalysisJobStore:
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
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL DEFAULT 'default',
                    analysis_mode TEXT NOT NULL DEFAULT 'standard',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(analysis_jobs)")}
            if "profile_id" not in columns:
                conn.execute(
                    "ALTER TABLE analysis_jobs ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default'"
                )
            if "analysis_mode" not in columns:
                conn.execute(
                    "ALTER TABLE analysis_jobs ADD COLUMN analysis_mode TEXT NOT NULL DEFAULT 'standard'"
                )
            conn.commit()

    def create_job(self, request: AnalysisJobCreateRequest) -> int:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO analysis_jobs (
                    profile_id,
                    analysis_mode,
                    status,
                    created_at,
                    updated_at,
                    request_json,
                    result_json,
                    error
                ) VALUES (?, ?, 'pending', ?, ?, ?, NULL, NULL)
                """,
                (
                    request.profile_id,
                    request.analysis_mode,
                    now,
                    now,
                    request.model_dump_json(),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_jobs(self, profile_id: str = "default", status: str | None = None, limit: int = 50) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 200))
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM analysis_jobs
                    WHERE profile_id = ? AND status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (profile_id, status, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM analysis_jobs
                    WHERE profile_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (profile_id, safe_limit),
                ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_job(self, job_id: int) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def next_pending_job(self, profile_id: str | None = None) -> dict[str, object] | None:
        with self._connect() as conn:
            if profile_id:
                row = conn.execute(
                    """
                    SELECT * FROM analysis_jobs
                    WHERE status = 'pending' AND profile_id = ?
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (profile_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM analysis_jobs
                    WHERE status = 'pending'
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def mark_running(self, job_id: int) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET status = 'running', updated_at = ?, error = NULL WHERE id = ?",
                (now, job_id),
            )
            conn.commit()

    def mark_completed(self, job_id: int, result_json: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'completed', updated_at = ?, result_json = ?, error = NULL
                WHERE id = ?
                """,
                (now, result_json, job_id),
            )
            conn.commit()

    def mark_failed(self, job_id: int, error: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'failed', updated_at = ?, error = ?
                WHERE id = ?
                """,
                (now, error, job_id),
            )
            conn.commit()

    def stats(self, profile_id: str = "default") -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
                FROM analysis_jobs
                WHERE profile_id = ?
                """,
                (profile_id,),
            ).fetchone()
        return {
            "pending": int(row["pending"] or 0),
            "running": int(row["running"] or 0),
            "completed": int(row["completed"] or 0),
            "failed": int(row["failed"] or 0),
        }

    def cleanup(self, profile_id: str = "default", older_than_iso: str | None = None) -> int:
        with self._connect() as conn:
            if older_than_iso:
                cursor = conn.execute(
                    """
                    DELETE FROM analysis_jobs
                    WHERE profile_id = ?
                      AND status IN ('completed', 'failed')
                      AND created_at < ?
                    """,
                    (profile_id, older_than_iso),
                )
            else:
                cursor = conn.execute(
                    """
                    DELETE FROM analysis_jobs
                    WHERE profile_id = ?
                      AND status IN ('completed', 'failed')
                    """,
                    (profile_id,),
                )
            conn.commit()
            return int(cursor.rowcount)

    def delete_job(self, job_id: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM analysis_jobs WHERE id = ?", (job_id,))
            conn.commit()
            return int(cursor.rowcount)

    def reset_to_pending(self, job_id: int) -> dict[str, object]:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise ValueError(f"analysis job {job_id} not found")
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'pending', updated_at = ?, error = NULL
                WHERE id = ?
                """,
                (now, job_id),
            )
            conn.commit()

        refreshed = self.get_job(job_id)
        assert refreshed is not None
        return refreshed

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        return {
            "job_id": int(row["id"]),
            "profile_id": str(row["profile_id"]),
            "analysis_mode": str(row["analysis_mode"]),
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "request": json.loads(str(row["request_json"])),
            "result": json.loads(str(row["result_json"])) if row["result_json"] else None,
            "error": str(row["error"]) if row["error"] else None,
        }
