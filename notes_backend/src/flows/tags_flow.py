"""
TagsFlow: canonical use-case layer for tag operations.

Provides:
- List tags
- Create tag (normalized)
- Rename tag (normalized, unique)
- Delete tag (cascades note association via FK)

This module exists to avoid scattered SQL for tags across route handlers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import sqlite3

from ..adapters.sqlite_db import SqliteDb, execute, sqlite_connection
from ..domain.models import TagCreate, TagListOut, TagOut, TagUpdate

logger = logging.getLogger("notes_backend.tags_flow")


class TagNotFoundError(Exception):
    """Raised when a requested tag does not exist."""


def _parse_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _normalize_tag(name: str) -> str:
    # Invariant: trimmed, lowercased, single spaces.
    return " ".join((name or "").strip().lower().split())


@dataclass(frozen=True)
class TagsFlow:
    """
    TagsFlow orchestrates tag operations.

    Contract:
      - Inputs: db dependency (SqliteDb)
      - Outputs: Pydantic response models (TagOut, TagListOut) or None for deletes.
      - Errors:
          - sqlite3.Error: DB errors (propagated)
          - TagNotFoundError: when tag doesn't exist
          - ValueError: invalid input (e.g., empty after normalization)
      - Side effects: reads/writes SQLite DB
    """

    db: SqliteDb

    def _get_tag_row(self, conn: sqlite3.Connection, tag_id: int) -> sqlite3.Row:
        cur = execute(conn, "SELECT * FROM tags WHERE id = ?", (tag_id,))
        row = cur.fetchone()
        if row is None:
            raise TagNotFoundError(f"Tag {tag_id} not found")
        return row

    def _row_to_tag_out(self, row: sqlite3.Row) -> TagOut:
        return TagOut(id=int(row["id"]), name=row["name"], created_at=_parse_dt(row["created_at"]))

    # PUBLIC_INTERFACE
    def list_tags(self, q: Optional[str] = None, limit: int = 200, offset: int = 0) -> TagListOut:
        """
        List tags with optional query/pagination.

        Search behavior:
          - matches tag name with LIKE (case-insensitive via lower()).
        """
        q = (q or "").strip()
        logger.info("TagsFlow.list_tags start q=%s limit=%s offset=%s", bool(q), limit, offset)

        where: List[str] = []
        params: List[object] = []
        if q:
            where.append("lower(name) LIKE ?")
            params.append(f"%{q.lower()}%")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        with sqlite_connection(self.db) as conn:
            cur_total = execute(conn, f"SELECT COUNT(*) AS c FROM tags {where_sql}", tuple(params))
            total = int(cur_total.fetchone()["c"])

            cur = execute(
                conn,
                f"""
                SELECT *
                FROM tags
                {where_sql}
                ORDER BY name ASC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset]),
            )
            rows = cur.fetchall()
            items = [self._row_to_tag_out(r) for r in rows]

        logger.info("TagsFlow.list_tags end total=%s returned=%s", total, len(items))
        return TagListOut(items=items, total=total)

    # PUBLIC_INTERFACE
    def create_tag(self, payload: TagCreate) -> TagOut:
        """Create a tag (idempotent by name due to UNIQUE constraint)."""
        name = _normalize_tag(payload.name)
        if not name:
            raise ValueError("Tag name is required.")
        logger.info("TagsFlow.create_tag start name=%s", name)

        with sqlite_connection(self.db) as conn:
            execute(conn, "INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
            cur = execute(conn, "SELECT * FROM tags WHERE name = ?", (name,))
            row = cur.fetchone()
            # Should always exist after insert-or-ignore.
            if row is None:
                raise sqlite3.Error("Failed to create/read back tag.")
            out = self._row_to_tag_out(row)

        logger.info("TagsFlow.create_tag end id=%s", out.id)
        return out

    # PUBLIC_INTERFACE
    def rename_tag(self, tag_id: int, payload: TagUpdate) -> TagOut:
        """Rename a tag by id."""
        if payload.name is None:
            raise ValueError("Tag name is required.")
        name = _normalize_tag(payload.name)
        if not name:
            raise ValueError("Tag name is required.")
        logger.info("TagsFlow.rename_tag start id=%s name=%s", tag_id, name)

        with sqlite_connection(self.db) as conn:
            _ = self._get_tag_row(conn, tag_id)
            execute(conn, "UPDATE tags SET name = ? WHERE id = ?", (name, tag_id))
            row = self._get_tag_row(conn, tag_id)
            out = self._row_to_tag_out(row)

        logger.info("TagsFlow.rename_tag end id=%s", out.id)
        return out

    # PUBLIC_INTERFACE
    def delete_tag(self, tag_id: int) -> None:
        """Delete a tag by id. note_tags rows cascade due to FK."""
        logger.info("TagsFlow.delete_tag start id=%s", tag_id)
        with sqlite_connection(self.db) as conn:
            cur = execute(conn, "DELETE FROM tags WHERE id = ?", (tag_id,))
            if cur.rowcount == 0:
                raise TagNotFoundError(f"Tag {tag_id} not found")
        logger.info("TagsFlow.delete_tag end id=%s", tag_id)
