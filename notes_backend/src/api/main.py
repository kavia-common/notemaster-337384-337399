"""
notes_backend FastAPI application.

Provides REST APIs for a Notes app:
- CRUD notes
- list/search notes
- optional tag filtering

Environment variables:
- SQLITE_DB: path to SQLite database file (provided by database container)
- CORS_ALLOW_ORIGINS: comma-separated list or "*" (default)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ..core.config import get_config
from ..adapters.sqlite_db import SqliteDb
from ..domain.models import NoteCreate, NoteListOut, NoteOut, NoteUpdate
from ..flows.notes_flow import NotesFlow, NoteNotFoundError

logging.basicConfig(level=logging.INFO)

openapi_tags = [
    {"name": "Health", "description": "Service health and diagnostics."},
    {"name": "Notes", "description": "Create, read, update, delete, list/search notes with optional tags."},
]

app = FastAPI(
    title="NoteMaster API",
    description="Backend APIs for NoteMaster notes application.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

cfg = get_config()
db = SqliteDb(path=cfg.sqlite_db_path)
flow = NotesFlow(db=db)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"], summary="Health check", operation_id="health_check")
def health_check():
    """Return a simple health response to indicate the service is running."""
    return {"message": "Healthy"}


@app.get(
    "/notes",
    response_model=NoteListOut,
    tags=["Notes"],
    summary="List notes",
    description="List notes with optional free-text search (q) and optional tag filter.",
    operation_id="list_notes",
)
def list_notes(
    q: str | None = Query(default=None, description="Optional search query (matches title/content)."),
    tag: str | None = Query(default=None, description="Optional tag filter (tag name)."),
    limit: int = Query(default=50, ge=1, le=100, description="Max items to return (1-100)."),
    offset: int = Query(default=0, ge=0, description="Offset for pagination."),
):
    """List notes with optional search/tag filter and pagination."""
    return flow.list_notes(q=q, tag=tag, limit=limit, offset=offset)


@app.post(
    "/notes",
    response_model=NoteOut,
    tags=["Notes"],
    summary="Create note",
    description="Create a new note with optional tags.",
    operation_id="create_note",
)
def create_note(payload: NoteCreate):
    """Create a note."""
    return flow.create_note(payload)


@app.get(
    "/notes/{note_id}",
    response_model=NoteOut,
    tags=["Notes"],
    summary="Get note",
    description="Fetch a single note by id.",
    operation_id="get_note",
)
def get_note(note_id: int):
    """Get note by id."""
    try:
        return flow.get_note(note_id)
    except NoteNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.patch(
    "/notes/{note_id}",
    response_model=NoteOut,
    tags=["Notes"],
    summary="Update note",
    description="Partially update a note. If tags are provided they replace existing tags.",
    operation_id="update_note",
)
def update_note(note_id: int, payload: NoteUpdate):
    """Update note by id."""
    try:
        return flow.update_note(note_id, payload)
    except NoteNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.delete(
    "/notes/{note_id}",
    tags=["Notes"],
    summary="Delete note",
    description="Delete a note by id.",
    operation_id="delete_note",
)
def delete_note(note_id: int):
    """Delete note by id."""
    try:
        flow.delete_note(note_id)
        return {"deleted": True, "id": note_id}
    except NoteNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
