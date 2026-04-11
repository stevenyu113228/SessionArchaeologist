"""Turn endpoints — paginated access to session turns."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.api.routes.sessions import _find_session
from archaeologist.db.models import Turn

router = APIRouter()


class TurnOut(BaseModel):
    id: str
    turn_index: int
    role: str
    content_text: str
    tool_calls: Optional[list] = None
    is_compact_boundary: bool
    is_error: bool
    token_estimate: int
    timestamp: Optional[str] = None
    model_used: Optional[str] = None
    has_thinking: bool = False
    is_sidechain: bool = False

    class Config:
        from_attributes = True


class TurnsPage(BaseModel):
    items: list[TurnOut]
    total: int
    offset: int
    limit: int


@router.get("/{session_id}/turns", response_model=TurnsPage)
def list_turns(
    session_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    role: Optional[str] = Query(None),
    errors_only: bool = Query(False),
    db: DBSession = Depends(get_db),
):
    session = _find_session(db, session_id)
    q = db.query(Turn).filter(Turn.session_id == session.id)

    if role:
        q = q.filter(Turn.role == role)
    if errors_only:
        q = q.filter(Turn.is_error == True)

    total = q.count()
    turns = q.order_by(Turn.turn_index).offset(offset).limit(limit).all()

    return TurnsPage(
        items=[
            TurnOut(
                id=str(t.id),
                turn_index=t.turn_index,
                role=t.role,
                content_text=t.content_text,
                tool_calls=t.tool_calls,
                is_compact_boundary=t.is_compact_boundary,
                is_error=t.is_error,
                token_estimate=t.token_estimate,
                timestamp=t.timestamp.isoformat() if t.timestamp else None,
                model_used=t.model_used,
                has_thinking=t.has_thinking,
                is_sidechain=t.is_sidechain,
            )
            for t in turns
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{session_id}/turns/{turn_index}")
def get_turn(session_id: str, turn_index: int, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    turn = (
        db.query(Turn)
        .filter(Turn.session_id == session.id, Turn.turn_index == turn_index)
        .first()
    )
    if not turn:
        from fastapi import HTTPException
        raise HTTPException(404, f"Turn {turn_index} not found")

    return TurnOut(
        id=str(turn.id),
        turn_index=turn.turn_index,
        role=turn.role,
        content_text=turn.content_text,
        tool_calls=turn.tool_calls,
        is_compact_boundary=turn.is_compact_boundary,
        is_error=turn.is_error,
        token_estimate=turn.token_estimate,
        timestamp=turn.timestamp.isoformat() if turn.timestamp else None,
        model_used=turn.model_used,
        has_thinking=turn.has_thinking,
        is_sidechain=turn.is_sidechain,
    )
