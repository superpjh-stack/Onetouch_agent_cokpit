from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .data_hub import OnetouchRepository


class _ConnectionAdapter:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @staticmethod
    def _sql(sql: str) -> str:
        statement = sql.replace("?", "%s")
        if "INSERT OR IGNORE INTO" in statement:
            statement = statement.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            statement = statement.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        if "INSERT OR REPLACE INTO settings" in statement:
            statement = statement.replace("INSERT OR REPLACE INTO settings", "INSERT INTO settings")
            statement = statement.rstrip().rstrip(";") + " ON CONFLICT (setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value"
        return statement

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self.connection.execute(self._sql(sql), params)

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> Any:
        return self.connection.executemany(self._sql(sql), rows)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def __enter__(self) -> "_ConnectionAdapter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.connection.close()


class PostgresOnetouchRepository(OnetouchRepository):
    """PostgreSQL + pgvector operational backend with the same read-only API."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.db_path = Path("postgresql")
        self.docs_dir = Path(__file__).resolve().parents[1] / "sample_docs"
        self._enable_vector_extension()
        self._initialize()
        with self._connect() as connection:
            connection.execute("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS embedding vector(1536)")
            connection.execute("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS embedding_model TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS knowledge_documents_embedding_hnsw ON knowledge_documents USING hnsw (embedding vector_cosine_ops)")

    def _raw_connect(self, register: bool = True) -> Any:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        if register:
            try:
                from pgvector.psycopg import register_vector
                register_vector(connection)
            except Exception:
                connection.close()
                raise
        return connection

    def _enable_vector_extension(self) -> None:
        connection = self._raw_connect(register=False)
        try:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> _ConnectionAdapter:
        return _ConnectionAdapter(self._raw_connect())

    @staticmethod
    def _dicts(rows: list[Any]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def browse_table(self, table: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if table not in self.TABLE_LABELS:
            raise ValueError(f"조회가 허용되지 않은 테이블: {table}")
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        return self._query(f"SELECT * FROM {table} ORDER BY 1 LIMIT ? OFFSET ?", (safe_limit, safe_offset))


def create_repository(sqlite_path: str | Path) -> OnetouchRepository:
    database_url = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if database_url:
        return PostgresOnetouchRepository(database_url)
    return OnetouchRepository(sqlite_path)
