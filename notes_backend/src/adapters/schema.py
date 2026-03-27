"""
SQLite schema initialization and lightweight migrations.

This backend uses raw sqlite3 without an ORM. To keep deployments simple, we:
- Ensure base tables exist at startup (CREATE TABLE IF NOT EXISTS).
- Apply additive migrations (e.g., adding new columns) in a safe, idempotent way.

This module must stay conservative: only additive changes, no destructive migrations.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from .sqlite_db import SqliteDb, execute, sqlite_connection

logger = logging.getLogger("notes_backend.sqlite_schema")


@dataclass(frozen=True)
class Migration:
    """Represents a single SQL migration statement."""
    name: str
    sql: str


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = execute(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,))
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = execute(conn, f"PRAGMA table_info({table})")
    cols = [r["name"] for r in cur.fetchall()]
    return column in cols


def _apply_migrations(conn: sqlite3.Connection, migrations: Iterable[Migration]) -> None:
    for m in migrations:
        logger.info("Applying migration: %s", m.name)
        execute(conn, m.sql)


# PUBLIC_INTERFACE
def ensure_schema(db: SqliteDb) -> None:
    """
    Ensure the SQLite schema exists and is up to date.

    Contract:
      - Inputs: SqliteDb (path)
      - Output: None
      - Errors: sqlite3.Error for any DB problems
      - Side effects: creates tables, adds columns (additive migrations)
    """
    with sqlite_connection(db) as conn:
        # Base tables (idempotent).
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS notes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                -- Favorites/star feature (added via migration if missing)
                starred INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )

        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS tags(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """,
        )

        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS note_tags(
                note_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (note_id, tag_id),
                FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
            """,
        )

        # Additive migrations for older DBs.
        # If an existing DB was created before "starred" existed, add it safely.
        if _table_exists(conn, "notes") and not _column_exists(conn, "notes", "starred"):
            _apply_migrations(
                conn,
                [
                    Migration(
                        name="add_notes_starred_column",
                        sql="ALTER TABLE notes ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
                    )
                ],
            )

        # Helpful indexes (idempotent).
        execute(conn, "CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at)")
        execute(conn, "CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(pinned)")
        execute(conn, "CREATE INDEX IF NOT EXISTS idx_notes_starred ON notes(starred)")
        execute(conn, "CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
        execute(conn, "CREATE INDEX IF NOT EXISTS idx_note_tags_note_id ON note_tags(note_id)")
        execute(conn, "CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id)")
