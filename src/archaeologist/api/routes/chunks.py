"""Chunk endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.api.routes.sessions import _find_session
from archaeologist.db.models import Chunk

router = APIRouter()


class ChunkOut(BaseModel):
    id: str
    chunk_index: int
    start_turn: int
    end_turn: int
    overlap_start_turn: Optional[int] = None
    token_estimate: int
    hot_zone_count: int
    contains_compact_boundary: bool
    extraction_status: str
    extraction_result: Optional[dict] = None
    extraction_model: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/{session_id}/chunks", response_model=list[ChunkOut])
def list_chunks(session_id: str, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    chunks = db.query(Chunk).filter(Chunk.session_id == session.id).order_by(Chunk.chunk_index).all()
    return [
        ChunkOut(
            id=str(c.id),
            chunk_index=c.chunk_index,
            start_turn=c.start_turn,
            end_turn=c.end_turn,
            overlap_start_turn=c.overlap_start_turn,
            token_estimate=c.token_estimate,
            hot_zone_count=c.hot_zone_count,
            contains_compact_boundary=c.contains_compact_boundary,
            extraction_status=c.extraction_status,
            extraction_result=c.extraction_result,
            extraction_model=c.extraction_model,
        )
        for c in chunks
    ]


@router.get("/{session_id}/chunks/{chunk_id}/result")
def get_chunk_result(session_id: str, chunk_id: str, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    chunk = db.query(Chunk).filter(Chunk.session_id == session.id, Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(404, "Chunk not found")
    return {"extraction_result": chunk.extraction_result, "status": chunk.extraction_status}
