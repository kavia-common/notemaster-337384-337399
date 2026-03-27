"""
NotesFlow: canonical use-case layer for note operations.

This module centralizes CRUD/search logic to avoid duplicated mini-flows
across route handlers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import sqlite3

from ..adapters.sqlite_db import SqliteDb, sqlite_connection, execute
from ..domain.models import NoteCreate, NoteListOut, NoteOut, NoteUpdate

logger = logging.getLogger("notes_backend.notes_flow")


class NoteNotFoundError(Exception):
    """Raised when a requested note does not exist."""


def _parse_dt(s: str) -> datetime:
    # Stored as ISO-ish string with Z; handle robustly.
    # Example: 2025-01-01T12:34:56.123Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _normalize_tags(tags: List[str]) -> List[str]:
    # Invariant: lowercased, trimmed, unique, stable order.
    seen = set()
    out: List[str] = []
    for t in tags:
        nt = (t or "").strip().lower()
        if not nt:
            continue
        if nt in seen:
            continue
        seen.add(nt)
        out.append(nt)
    return out


@dataclass(frozen=True)
class NotesFlow:
    """
    NotesFlow orchestrates all note operations.

    Contract:
      - Inputs: db dependency (SqliteDb)
      - Outputs: Pydantic response models (NoteOut, NoteListOut) or None for deletes.
      - Errors:
          - sqlite3.Error: DB errors (propagated)
          - NoteNotFoundError: when note doesn't exist
      - Side effects: reads/writes SQLite DB
    """

    db: SqliteDb

    def _get_note_row(self, conn: sqlite3.Connection, note_id: int) -> sqlite3.Row:
        cur = execute(conn, "SELECT * FROM notes WHERE id = ?", (note_id,))
        row = cur.fetchone()
        if row is None:
            raise NoteNotFoundError(f"Note {note_id} not found")
        return row

    def _get_note_tags(self, conn: sqlite3.Connection, note_id: int) -> List[str]:
        cur = execute(
            conn,
            """
            SELECT t.name
            FROM tags t
            JOIN note_tags nt ON nt.tag_id = t.id
            WHERE nt.note_id = ?
            ORDER BY t.name ASC
            """,
            (note_id,),
        )
        return [r["name"] for r in cur.fetchall()]

    def _ensure_tags(self, conn: sqlite3.Connection, tags: List[str]) -> List[int]:
        tag_ids: List[int] = []
        for name in tags:
            execute(conn, "INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
            cur = execute(conn, "SELECT id FROM tags WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                tag_ids.append(int(row["id"]))
        return tag_ids

    def _replace_note_tags(self, conn: sqlite3.Connection, note_id: int, tags: List[str]) -> None:
        execute(conn, "DELETE FROM note_tags WHERE note_id = ?", (note_id,))
        if not tags:
            return
        tag_ids = self._ensure_tags(conn, tags)
        for tag_id in tag_ids:
            execute(conn, "INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?, ?)", (note_id, tag_id))

    def _row_to_note_out(self, conn: sqlite3.Connection, row: sqlite3.Row) -> NoteOut:
        note_id = int(row["id"])
        tags = self._get_note_tags(conn, note_id)
        return NoteOut(
            id=note_id,
            title=row["title"],
            content=row["content"],
            tags=tags,
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
        )

    # PUBLIC_INTERFACE
    def create_note(self, payload: NoteCreate) -> NoteOut:
        """
        Create a note.

        Inputs:
          - payload: NoteCreate (title, content, optional tags)
        Output:
          - NoteOut
        """
        norm_tags = _normalize_tags(payload.tags)
        logger.info("NotesFlow.create_note start title_len=%s tags=%s", len(payload.title), len(norm_tags))

        with sqlite_connection(self.db) as conn:
            now = _now_iso_z()
            cur = execute(
                conn,
                """
                INSERT INTO notes(title, content, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (payload.title.strip(), payload.content, now, now),
            )
            note_id = int(cur.lastrowid)
            self._replace_note_tags(conn, note_id, norm_tags)
            row = self._get_note_row(conn, note_id)
            result = self._row_to_note_out(conn, row)

        logger.info("NotesFlow.create_note end id=%s", result.id)
        return result

    # PUBLIC_INTERFACE
    def get_note(self, note_id: int) -> NoteOut:
        """Fetch a note by id."""
        logger.info("NotesFlow.get_note start id=%s", note_id)
        with sqlite_connection(self.db) as conn:
            row = self._get_note_row(conn, note_id)
            result = self._row_to_note_out(conn, row)
        logger.info("NotesFlow.get_note end id=%s", note_id)
        return result

    # PUBLIC_INTERFACE
    def update_note(self, note_id: int, payload: NoteUpdate) -> NoteOut:
        """
        Update a note (partial update).

        Rules:
          - title/content set when provided.
          - tags: if provided, replaces existing tags.
        """
        logger.info("NotesFlow.update_note start id=%s", note_id)
        with sqlite_connection(self.db) as conn:
            _ = self._get_note_row(conn, note_id)

            fields: List[Tuple[str, object]] = []
            if payload.title is not None:
                fields.append(("title", payload.title.strip()))
            if payload.content is not None:
                fields.append(("content", payload.content))

            if fields:
                set_sql = ", ".join([f"{k} = ?" for k, _ in fields] + ["updated_at = ?"])
                params = tuple([v for _, v in fields] + [_now_iso_z(), note_id])
                execute(conn, f"UPDATE notes SET {set_sql} WHERE id = ?", params)

            if payload.tags is not None:
                self._replace_note_tags(conn, note_id, _normalize_tags(payload.tags))

            row = self._get_note_row(conn, note_id)
            result = self._row_to_note_out(conn, row)

        logger.info("NotesFlow.update_note end id=%s", note_id)
        return result

    # PUBLIC_INTERFACE
    def delete_note(self, note_id: int) -> None:
        """Delete a note by id."""
        logger.info("NotesFlow.delete_note start id=%s", note_id)
        with sqlite_connection(self.db) as conn:
            cur = execute(conn, "DELETE FROM notes WHERE id = ?", (note_id,))
            if cur.rowcount == 0:
                raise NoteNotFoundError(f"Note {note_id} not found")
        logger.info("NotesFlow.delete_note end id=%s", note_id)

    # PUBLIC_INTERFACE
    def list_notes(
        self,
        q: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NoteListOut:
        """
        List notes with optional search and tag filter.

        Search behavior:
          - matches title/content with LIKE (case-insensitive via lower()).

        Tag behavior:
          - filters notes that have the provided tag name (case-insensitive).

        Pagination:
          - limit/max 100 enforced at API layer; offset >= 0.
        """
        q = (q or "").strip()
        tag = (tag or "").strip().lower() or None

        logger.info("NotesFlow.list_notes start q=%s tag=%s limit=%s offset=%s", bool(q), tag, limit, offset)

        where: List[str] = []
        params: List[object] = []

        join = ""
        if tag:
            join = "JOIN note_tags nt ON nt.note_id = n.id JOIN tags t ON t.id = nt.tag_id"
            where.append("t.name = ?")
            params.append(tag)

        if q:
            where.append("(lower(n.title) LIKE ? OR lower(n.content) LIKE ?)")
            like = f"%{q.lower()}%"
            params.extend([like, like])

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        with sqlite_connection(self.db) as conn:
            cur_total = execute(
                conn,
                f"""
                SELECT COUNT(DISTINCT n.id) AS c
                FROM notes n
                {join}
                {where_sql}
                """,
                tuple(params),
            )
            total = int(cur_total.fetchone()["c"])

            cur = execute(
                conn,
                f"""
                SELECT DISTINCT n.*
                FROM notes n
                {join}
                {where_sql}
                ORDER BY n.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset]),
            )
            rows = cur.fetchall()
            items = [self._row_to_note_out(conn, r) for r in rows]

        logger.info("NotesFlow.list_notes end total=%s returned=%s", total, len(items))
        return NoteListOut(items=items, total=total)
