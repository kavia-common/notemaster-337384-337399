"""
SQLite adapter for notes_backend.

This module is the I/O boundary to SQLite. Domain logic should not directly
open connections or execute SQL outside this adapter.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass(frozen=True)
class SqliteDb:
    """Holds sqlite database path."""
    path: str


# PUBLIC_INTERFACE
@contextmanager
def sqlite_connection(db: SqliteDb) -> Iterator[sqlite3.Connection]:
    """
    Context manager providing a sqlite3 connection.

    Contract:
      - Inputs: SqliteDb with a file path.
      - Output: yields sqlite3.Connection with Row factory.
      - Errors: raises sqlite3.Error on connection issues.
      - Side effects: opens and closes a database connection.
    """
    conn = sqlite3.connect(db.path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(conn: sqlite3.Connection, sql: str, params: Optional[tuple] = None) -> sqlite3.Cursor:
    """Execute a statement and return cursor."""
    if params is None:
        return conn.execute(sql)
    return conn.execute(sql, params)
