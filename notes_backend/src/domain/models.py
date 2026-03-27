"""
Pydantic models for the NoteMaster API.

All public API request/response shapes live here to keep contracts explicit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class NoteBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Short note title.")
    content: str = Field(..., min_length=1, description="Note body content (plain text).")
    tags: List[str] = Field(default_factory=list, description="Optional list of tag names.")
    pinned: bool = Field(default=False, description="Whether the note is pinned to the top of the list.")


class NoteCreate(NoteBase):
    """Request payload to create a note."""


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="Updated title.")
    content: Optional[str] = Field(None, min_length=1, description="Updated note content.")
    tags: Optional[List[str]] = Field(None, description="Replace tags with this list; omit to keep unchanged.")
    pinned: Optional[bool] = Field(None, description="Set pinned state; omit to keep unchanged.")


class NoteOut(BaseModel):
    id: int = Field(..., description="Note ID.")
    title: str = Field(..., description="Note title.")
    content: str = Field(..., description="Note content.")
    tags: List[str] = Field(default_factory=list, description="Tag names.")
    pinned: bool = Field(default=False, description="Whether the note is pinned to the top of the list.")
    created_at: datetime = Field(..., description="Creation time (UTC).")
    updated_at: datetime = Field(..., description="Last update time (UTC).")


class NoteListOut(BaseModel):
    items: List[NoteOut] = Field(..., description="Notes list items.")
    total: int = Field(..., description="Total items matching query.")


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Tag name (will be normalized).")


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50, description="New tag name (normalized).")


class TagOut(BaseModel):
    id: int = Field(..., description="Tag ID.")
    name: str = Field(..., description="Tag name.")
    created_at: datetime = Field(..., description="Creation time (UTC).")


class TagListOut(BaseModel):
    items: List[TagOut] = Field(..., description="Tags list items.")
    total: int = Field(..., description="Total tags.")
