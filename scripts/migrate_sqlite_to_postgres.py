from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from onetouch_agent.postgres_hub import PostgresOnetouchRepository


TABLES = [
    "quote_requests", "drawings", "manufacturing_features", "bom_items", "routings",
    "cost_estimates", "quote_history", "material_inventory", "approval_queue",
    "order_feedback", "knowledge_documents", "rules", "settings",
]


def migrate(sqlite_path: Path, database_url: str, replace: bool = True) -> None:
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    target = PostgresOnetouchRepository(database_url)
    try:
        with target._connect() as connection:
            if replace:
                for table in reversed(TABLES):
                    connection.execute(f"DELETE FROM {table}")
            for table in TABLES:
                rows = source.execute(f"SELECT * FROM {table}").fetchall()
                if not rows:
                    continue
                columns = list(rows[0].keys())
                placeholders = ",".join("?" for _ in columns)
                values = [tuple(row[column] for column in columns) for row in rows]
                connection.executemany(
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                    values,
                )
    finally:
        source.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="원터치 SQLite 데모를 PostgreSQL로 이전합니다.")
    parser.add_argument("--sqlite", type=Path, default=Path("data/onetouch_demo.db"))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--append", action="store_true", help="대상 데이터를 지우지 않고 없는 행만 추가")
    args = parser.parse_args()
    migrate(args.sqlite, args.database_url, replace=not args.append)
    print("마이그레이션 완료")
