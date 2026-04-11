"""Pipeline control endpoints — trigger stages, check status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.api.routes.sessions import _find_session
from archaeologist.config import settings

router = APIRouter()


class PipelineStatus(BaseModel):
    session_id: str
    session_name: str
    status: str
    total_turns: int
    total_chunks: int
    extracted_chunks: int
    total_narratives: int


@router.get("/pipeline/{session_id}", response_model=PipelineStatus)
def get_pipeline_status(session_id: str, db: DBSession = Depends(get_db)):
    from archaeologist.db.models import Chunk, Narrative

    session = _find_session(db, session_id)
    total_chunks = db.query(Chunk).filter(Chunk.session_id == session.id).count()
    extracted = db.query(Chunk).filter(Chunk.session_id == session.id, Chunk.extraction_status == "done").count()
    narr_count = db.query(Narrative).filter(Narrative.session_id == session.id).count()

    return PipelineStatus(
        session_id=str(session.id),
        session_name=session.name,
        status=session.status,
        total_turns=session.total_turns,
        total_chunks=total_chunks,
        extracted_chunks=extracted,
        total_narratives=narr_count,
    )


class ChunkRequest(BaseModel):
    pass


@router.post("/sessions/{session_id}/chunk")
def trigger_chunking(session_id: str, db: DBSession = Depends(get_db)):
    from archaeologist.chunker.engine import chunk_session
    from archaeologist.db.models import Chunk, Turn

    session = _find_session(db, session_id)
    turns = db.query(Turn).filter(Turn.session_id == session.id).order_by(Turn.turn_index).all()

    if not turns:
        raise HTTPException(400, "No turns found")

    turn_dicts = [
        {
            "turn_index": t.turn_index,
            "token_estimate": t.token_estimate,
            "timestamp": t.timestamp,
            "role": t.role,
            "is_compact_boundary": t.is_compact_boundary,
            "is_error": t.is_error,
            "tool_calls": t.tool_calls,
            "content_text": t.content_text,
        }
        for t in turns
    ]

    chunks = chunk_session(turn_dicts, session.manifest or {})

    db.query(Chunk).filter(Chunk.session_id == session.id).delete()
    for cd in chunks:
        c = Chunk(
            session_id=session.id,
            chunk_index=cd["chunk_index"],
            start_turn=cd["start_turn"],
            end_turn=cd["end_turn"],
            overlap_start_turn=cd.get("overlap_start_turn"),
            token_estimate=cd["token_estimate"],
            hot_zone_count=cd["hot_zone_count"],
            contains_compact_boundary=cd["contains_compact_boundary"],
        )
        db.add(c)

    session.status = "chunked"
    db.commit()
    return {"chunks_created": len(chunks)}


@router.post("/sessions/{session_id}/extract")
def trigger_extraction(session_id: str, db: DBSession = Depends(get_db)):
    from archaeologist.db.models import Chunk, Turn
    from archaeologist.extractor.agent import extract_chunk

    session = _find_session(db, session_id)
    chunks = db.query(Chunk).filter(Chunk.session_id == session.id).order_by(Chunk.chunk_index).all()

    if not chunks:
        raise HTTPException(400, "No chunks. Run chunking first.")

    total_chunks = len(chunks)
    for c in chunks:
        if c.extraction_status == "done":
            continue

        turns = (
            db.query(Turn)
            .filter(Turn.session_id == session.id, Turn.turn_index >= c.start_turn, Turn.turn_index <= c.end_turn)
            .order_by(Turn.turn_index)
            .all()
        )

        result = extract_chunk(
            turns=turns,
            chunk_id=c.chunk_index,
            total_chunks=total_chunks,
            has_overlap=c.overlap_start_turn is not None,
            overlap_tokens=0,
            model=settings.extraction_model,
        )

        c.extraction_result = result
        c.extraction_status = "done"
        c.extraction_model = settings.extraction_model
        db.commit()

    session.status = "extracted"
    db.commit()
    return {"extracted": total_chunks}


@router.post("/sessions/{session_id}/synthesize")
def trigger_synthesis(session_id: str, db: DBSession = Depends(get_db)):
    from sqlalchemy import func

    from archaeologist.db.models import Chunk, Narrative
    from archaeologist.synthesizer.agent import synthesize_narrative

    session = _find_session(db, session_id)
    chunks = (
        db.query(Chunk)
        .filter(Chunk.session_id == session.id, Chunk.extraction_status == "done")
        .order_by(Chunk.chunk_index)
        .all()
    )

    if not chunks:
        raise HTTPException(400, "No extracted chunks. Run extraction first.")

    extractions = [c.extraction_result for c in chunks]
    narrative_md = synthesize_narrative(extractions, model=settings.synthesis_model)

    max_rev = db.query(func.max(Narrative.revision)).filter(Narrative.session_id == session.id).scalar()
    revision = (max_rev or 0) + 1

    narr = Narrative(
        session_id=session.id,
        revision=revision,
        content_md=narrative_md,
        synthesis_model=settings.synthesis_model,
    )
    db.add(narr)
    session.status = "synthesized"
    db.commit()

    return {"revision": revision, "content_length": len(narrative_md)}


@router.get("/config")
def get_config():
    return {
        "extraction_model": settings.extraction_model,
        "synthesis_model": settings.synthesis_model,
        "refinement_model": settings.refinement_model,
        "chunk_target_tokens": settings.chunk_target_tokens,
        "chunk_overlap_tokens": settings.chunk_overlap_tokens,
        "max_parallel_extractions": settings.max_parallel_extractions,
        "cost_confirmation_threshold": settings.cost_confirmation_threshold,
    }
