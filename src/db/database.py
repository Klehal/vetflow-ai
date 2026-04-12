"""Async SQLite database layer with migration support."""

import logging
import os
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger("vetflow.db")


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        logger.info(f"Connected to database: {self.db_path}")

    async def close(self):
        if self._db:
            await self._db.close()
            logger.info("Database connection closed")

    @property
    def db(self) -> aiosqlite.Connection:
        if not self._db:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    async def run_migrations(self, migrations_dir: str = "migrations"):
        """Run all SQL migration files in order."""
        migrations_path = Path(migrations_dir)
        if not migrations_path.exists():
            logger.warning(f"Migrations directory not found: {migrations_dir}")
            return

        sql_files = sorted(migrations_path.glob("*.sql"))
        for sql_file in sql_files:
            logger.info(f"Running migration: {sql_file.name}")
            sql = sql_file.read_text()
            await self._db.executescript(sql)

        await self._db.commit()
        logger.info(f"Ran {len(sql_files)} migrations")

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        cursor = await self.db.execute(sql, params)
        await self.db.commit()
        return cursor

    async def execute_many(self, sql: str, params_list: list):
        await self.db.executemany(sql, params_list)
        await self.db.commit()

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        cursor = await self.db.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self.db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def fetch_count(self, sql: str, params: tuple = ()) -> int:
        cursor = await self.db.execute(sql, params)
        row = await cursor.fetchone()
        return row[0] if row else 0
