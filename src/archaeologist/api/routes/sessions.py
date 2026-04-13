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


class SubagentOut(BaseModel):
    id: str
    name: str
    agent_type: Optional[str] = None
    agent_description: Optional[str] = None
    total_turns: int


class SessionOut(BaseModel):
    id: str
    name: str
    source_path: str
    imported_at: Optional[str] = None
    total_turns: int
    total_tokens_est: int
    manifest: Optional[dict] = None
    status: str
    session_type: str = "main"
    subagents: list[SubagentOut] = []
    parent_session_id: Optional[str] = None

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
def list_sessions(parent: Optional[str] = Query(None), db: DBSession = Depends(get_db)):
    q = db.query(Session)
    if parent:
        import uuid as _uuid
        try:
            pid = _uuid.UUID(parent)
            q = q.filter(Session.parent_session_id == pid)
        except ValueError:
            pass
    else:
        # By default, hide subagents from top-level list
        q = q.filter(Session.session_type != "subagent")
    sessions = q.order_by(Session.imported_at.desc()).all()
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

    subs = db.query(Session).filter(Session.parent_session_id == session.id).all()
    subagent_list = [
        SubagentOut(
            id=str(s.id), name=s.name, agent_type=s.agent_type,
            agent_description=s.agent_description, total_turns=s.total_turns,
        )
        for s in subs
    ]

    return SessionOut(
        id=str(session.id),
        name=session.name,
        source_path=session.source_path,
        imported_at=session.imported_at.isoformat() if session.imported_at else None,
        total_turns=session.total_turns,
        total_tokens_est=session.total_tokens_est,
        manifest=session.manifest,
        status=session.status,
        session_type=session.session_type,
        subagents=subagent_list,
        parent_session_id=str(session.parent_session_id) if session.parent_session_id else None,
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

    _store_turns(db, session.id, turns_data)

    db.commit()
    return {"id": str(session.id), "name": session_name, "total_turns": manifest["total_turns"]}


@router.post("/upload")
async def upload_session(
    file: UploadFile = File(...),
    name: Optional[str] = Query(None),
    db: DBSession = Depends(get_db),
):
    """Upload a .jsonl file to import a session."""
    from archaeologist.parser.jsonl import parse_jsonl_bytes

    if not file.filename or not file.filename.endswith(".jsonl"):
        raise HTTPException(400, "File must be a .jsonl file")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")

    turns_data, manifest = parse_jsonl_bytes(data, source_path=file.filename)
    session_name = name or manifest.get("session_slug") or file.filename.rsplit(".", 1)[0]

    from archaeologist.db.models import Turn

    session = Session(
        name=session_name,
        source_path=f"upload:{file.filename}",
        total_turns=manifest["total_turns"],
        total_tokens_est=manifest["total_tokens_est"],
        manifest=manifest,
        status="imported",
    )
    db.add(session)
    db.flush()

    _store_turns(db, session.id, turns_data)

    db.commit()
    return {"id": str(session.id), "name": session_name, "total_turns": manifest["total_turns"]}


def _sanitize_nul(obj):
    """Recursively strip NUL chars from strings in dicts/lists (PostgreSQL rejects them)."""
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    if isinstance(obj, dict):
        return {k: _sanitize_nul(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nul(v) for v in obj]
    return obj


def _store_turns(db: DBSession, session_id, turns_data: list[dict]):
    from archaeologist.db.models import Turn

    for td in turns_data:
        db.add(Turn(
            session_id=session_id,
            turn_index=td["turn_index"], role=td["role"],
            content_text=(td["content_text"] or "").replace("\x00", ""),
            tool_calls=_sanitize_nul(td["tool_calls"]),
            is_compact_boundary=td["is_compact_boundary"], is_error=td["is_error"],
            token_estimate=td["token_estimate"], content_hash=td["content_hash"],
            timestamp=td["timestamp"], raw_jsonl_line=_sanitize_nul(td["raw_jsonl_line"]),
            message_uuid=td["message_uuid"], parent_uuid=td["parent_uuid"],
            is_sidechain=td["is_sidechain"], model_used=td["model_used"],
            token_usage=_sanitize_nul(td["token_usage"]), has_thinking=td["has_thinking"],
        ))


@router.post("/upload-project")
async def upload_project(
    file: UploadFile = File(...),
    name: Optional[str] = Query(None),
    db: DBSession = Depends(get_db),
):
    """Upload a .zip project containing main session + subagent sessions."""
    from archaeologist.parser.jsonl import parse_project_zip

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "File must be a .zip file")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")

    project = parse_project_zip(data)
    main = project["main"]
    main_manifest = main["manifest"]
    session_name = name or main_manifest.get("session_slug") or file.filename.rsplit(".", 1)[0]

    parent = Session(
        name=session_name,
        source_path=f"upload-project:{file.filename}",
        total_turns=main_manifest["total_turns"],
        total_tokens_est=main_manifest["total_tokens_est"],
        manifest=main_manifest,
        status="imported",
        session_type="main",
    )
    db.add(parent)
    db.flush()
    _store_turns(db, parent.id, main["turns"])

    # Store additional sessions (other JSONL files in the project)
    additional_results = []
    for extra in project.get("additional_sessions", []):
        ex_manifest = extra["manifest"]
        ex_name = ex_manifest.get("session_slug") or extra["filename"][:40]
        child = Session(
            name=ex_name,
            source_path=f"session:{extra['filename']}",
            total_turns=ex_manifest["total_turns"],
            total_tokens_est=ex_manifest["total_tokens_est"],
            manifest=ex_manifest,
            status="imported",
            parent_session_id=parent.id,
            session_type="subagent",
            agent_type="session",
            agent_description=f"Additional session: {ex_name}",
        )
        db.add(child)
        db.flush()
        _store_turns(db, child.id, extra["turns"])
        additional_results.append({
            "id": str(child.id), "name": ex_name,
            "agent_type": "session", "description": f"Additional session ({ex_manifest['total_turns']} turns)",
            "total_turns": ex_manifest["total_turns"],
        })

    # Store subagents
    subagent_results = []
    for sa in project["subagents"]:
        sa_manifest = sa["manifest"]
        sa_name = sa["description"][:80] if sa["description"] else sa["agent_id"][:20]
        child = Session(
            name=sa_name,
            source_path=f"subagent:{sa['agent_id']}",
            total_turns=sa_manifest["total_turns"],
            total_tokens_est=sa_manifest["total_tokens_est"],
            manifest=sa_manifest,
            status="imported",
            parent_session_id=parent.id,
            session_type="subagent",
            agent_type=sa["agent_type"],
            agent_description=sa["description"],
        )
        db.add(child)
        db.flush()
        _store_turns(db, child.id, sa["turns"])
        subagent_results.append({
            "id": str(child.id), "name": sa_name,
            "agent_type": sa["agent_type"], "description": sa["description"],
            "total_turns": sa_manifest["total_turns"],
        })

    db.commit()
    return {
        "id": str(parent.id), "name": session_name,
        "total_turns": main_manifest["total_turns"],
        "additional_sessions": additional_results,
        "subagents": subagent_results,
    }


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
