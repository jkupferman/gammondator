from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


class DatabaseConfigError(RuntimeError):
    pass


class DBConnection:
    def __init__(self, conn: Any, is_postgres: bool) -> None:
        self._conn = conn
        self.is_postgres = is_postgres

    def __enter__(self) -> "DBConnection":
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()):
        sql = _to_postgres_params(query) if self.is_postgres else query
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


def _normalize_database_url(raw: str) -> str:
    # Heroku commonly uses postgres:// URLs; psycopg expects postgresql://
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://") :]
    return raw


def _to_postgres_params(query: str) -> str:
    # App queries only use qmark placeholders in SQL (?), no literal question marks.
    return query.replace("?", "%s")


class Database:
    def __init__(self, dsn_or_path: str) -> None:
        self.raw = dsn_or_path
        self.is_postgres = self._is_postgres_dsn(dsn_or_path)
        self.dsn = _normalize_database_url(dsn_or_path)
        if not self.is_postgres:
            Path(self.dsn).parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_postgres_dsn(value: str) -> bool:
        lowered = value.lower()
        return lowered.startswith("postgres://") or lowered.startswith("postgresql://")

    def connect(self) -> DBConnection:
        if self.is_postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except Exception as exc:  # pragma: no cover - only hit on postgres deployments without deps
                raise DatabaseConfigError(
                    "Postgres selected but psycopg is not installed. Install psycopg[binary]."
                ) from exc

            conn = psycopg.connect(self.dsn, row_factory=dict_row)
            return DBConnection(conn=conn, is_postgres=True)

        conn = sqlite3.connect(self.dsn)
        conn.row_factory = sqlite3.Row
        return DBConnection(conn=conn, is_postgres=False)


def resolve_db_dsn(default_sqlite_path: str = "gammondator.db") -> str:
    return os.getenv("DATABASE_URL") or os.getenv("GAMMONDATOR_DB_PATH", default_sqlite_path)
