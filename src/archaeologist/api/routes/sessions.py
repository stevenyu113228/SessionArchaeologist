"""Session endpoints."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.db.models import Session

router = APIRouter()


class SessionOut(BaseModel):
    id: str
    name: str
    source_path: str
    imported_at: Optional[str] = None
    total_turns: int
    total_tokens_est: int
    manifest: Optional[dict] = None
    status: str

    class Config:
        from_attributes = True


class SessionListOut(BaseModel):
    id: str
    name: str
    status: str
    total_turns: int
    total_tokens_est: int
    imported_at: Optional[str] = None


@router.get("", response_model=list[SessionListOut])
def list_sessions(db: DBSession = Depends(get_db)):
    sessions = db.query(Session).order_by(Session.imported_at.desc()).all()
    return [
        SessionListOut(
            id=str(s.id),
            name=s.name,
            status=s.status,
            total_turns=s.total_turns,
            total_tokens_est=s.total_tokens_est,
            imported_at=s.imported_at.isoformat() if s.imported_at else None,
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    return SessionOut(
        id=str(session.id),
        name=session.name,
        source_path=session.source_path,
        imported_at=session.imported_at.isoformat() if session.imported_at else None,
        total_turns=session.total_turns,
        total_tokens_est=session.total_tokens_est,
        manifest=session.manifest,
        status=session.status,
    )


class ImportRequest(BaseModel):
    path: str
    name: Optional[str] = None


@router.post("/import")
def import_session(req: ImportRequest, db: DBSession = Depends(get_db)):
    from archaeologist.parser.jsonl import parse_jsonl_file

    file_path = Path(req.path)
    if not file_path.exists():
        raise HTTPException(400, f"File not found: {req.path}")

    turns_data, manifest = parse_jsonl_file(file_path)
    session_name = req.name or manifest.get("session_slug") or file_path.stem

    from archaeologist.db.models import Turn

    session = Session(
        name=session_name,
        source_path=str(file_path),
        total_turns=manifest["total_turns"],
        total_tokens_est=manifest["total_tokens_est"],
        manifest=manifest,
        status="imported",
    )
    db.add(session)
    db.flush()

    for td in turns_data:
        turn = Turn(
            session_id=session.id,
            turn_index=td["turn_index"],
            role=td["role"],
            content_text=td["content_text"],
            tool_calls=td["tool_calls"],
            is_compact_boundary=td["is_compact_boundary"],
            is_error=td["is_error"],
            token_estimate=td["token_estimate"],
            content_hash=td["content_hash"],
            timestamp=td["timestamp"],
            raw_jsonl_line=td["raw_jsonl_line"],
            message_uuid=td["message_uuid"],
            parent_uuid=td["parent_uuid"],
            is_sidechain=td["is_sidechain"],
            model_used=td["model_used"],
            token_usage=td["token_usage"],
            has_thinking=td["has_thinking"],
        )
        db.add(turn)

    db.commit()
    return {"id": str(session.id), "name": session_name, "total_turns": manifest["total_turns"]}


@router.delete("/{session_id}")
def delete_session(session_id: str, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    db.delete(session)
    db.commit()
    return {"deleted": str(session.id)}


def _find_session(db: DBSession, session_id: str) -> Session:
    try:
        uid = uuid.UUID(session_id)
        session = db.query(Session).filter(Session.id == uid).first()
    except ValueError:
        session = None

    if not session:
        from sqlalchemy import String
        session = db.query(Session).filter(Session.id.cast(String).startswith(session_id)).first()

    if not session:
        raise HTTPException(404, f"Session not found: {session_id}")
    return session
