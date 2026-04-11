"""Search endpoint — RAG-powered session search."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.api.routes.sessions import _find_session

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    mode: str = "semantic"  # semantic, keyword, hybrid
    n_results: int = 10
    filters: Optional[dict] = None


class SearchResult(BaseModel):
    content_text: str
    turn_index: Optional[int] = None
    role: Optional[str] = None
    is_error: bool = False
    score: float = 0.0


@router.post("/{session_id}/search", response_model=dict)
def search_session(session_id: str, req: SearchRequest, db: DBSession = Depends(get_db)):
    from archaeologist.rag.store import search

    session = _find_session(db, session_id)

    results = search(
        session_id=str(session.id),
        query=req.query,
        mode=req.mode,
        n_results=req.n_results,
        filters=req.filters,
    )

    return {"results": results, "total": len(results), "query": req.query}


@router.post("/{session_id}/embed")
def embed_session(session_id: str, db: DBSession = Depends(get_db)):
    """Trigger embedding of all turns for a session."""
    from archaeologist.db.models import Turn
    from archaeologist.rag.store import embed_turns

    session = _find_session(db, session_id)
    turns = db.query(Turn).filter(Turn.session_id == session.id).order_by(Turn.turn_index).all()

    if not turns:
        raise HTTPException(400, "No turns found")

    count = embed_turns(str(session.id), turns)
    return {"embedded": count, "session_id": str(session.id)}
