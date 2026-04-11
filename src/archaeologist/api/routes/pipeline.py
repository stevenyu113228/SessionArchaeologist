"""Pipeline control endpoints — trigger stages, check status, SSE progress."""

from __future__ import annotations

import asyncio
import json
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.api.routes.sessions import _find_session
from archaeologist.config import settings

router = APIRouter()

# In-memory progress tracking for active pipeline stages
_extraction_progress: dict[str, list[dict]] = {}
_synthesis_progress: dict[str, list[dict]] = {}


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


def _extract_one_chunk(session_id_str: str, chunk_id, chunk_index: int, total_chunks: int,
                       start_turn: int, end_turn: int, overlap_start_turn, session_id_uuid):
    """Extract a single chunk in a worker thread (has its own DB session)."""
    from archaeologist.db.models import Chunk, Turn
    from archaeologist.db.session import SessionLocal
    from archaeologist.extractor.agent import extract_chunk

    db = SessionLocal()
    try:
        turns = (
            db.query(Turn)
            .filter(Turn.session_id == session_id_uuid, Turn.turn_index >= start_turn, Turn.turn_index <= end_turn)
            .order_by(Turn.turn_index)
            .all()
        )

        chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
        if not chunk:
            return

        chunk.extraction_status = "processing"
        db.commit()

        # Push progress event
        _push_progress(session_id_str, {
            "type": "chunk_start",
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
        })

        t0 = time.time()
        result = extract_chunk(
            turns=turns,
            chunk_id=chunk_index,
            total_chunks=total_chunks,
            has_overlap=overlap_start_turn is not None,
            overlap_tokens=0,
            model=settings.extraction_model,
        )
        elapsed = time.time() - t0

        chunk.extraction_result = result
        chunk.extraction_status = "done"
        chunk.extraction_model = settings.extraction_model
        db.commit()

        _push_progress(session_id_str, {
            "type": "chunk_done",
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "elapsed_seconds": round(elapsed, 1),
        })
    except Exception as e:
        try:
            chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
            if chunk:
                chunk.extraction_status = "failed"
                db.commit()
        except Exception:
            pass
        _push_progress(session_id_str, {
            "type": "chunk_error",
            "chunk_index": chunk_index,
            "error": str(e),
        })
    finally:
        db.close()


def _push_progress(session_id: str, event: dict):
    if session_id not in _extraction_progress:
        _extraction_progress[session_id] = []
    _extraction_progress[session_id].append(event)


@router.post("/sessions/{session_id}/extract")
def trigger_extraction(session_id: str, db: DBSession = Depends(get_db)):
    """Launch parallel extraction in background threads, return immediately."""
    from archaeologist.db.models import Chunk

    session = _find_session(db, session_id)
    chunks = db.query(Chunk).filter(Chunk.session_id == session.id).order_by(Chunk.chunk_index).all()

    if not chunks:
        raise HTTPException(400, "No chunks. Run chunking first.")

    pending = [c for c in chunks if c.extraction_status != "done"]
    if not pending:
        session.status = "extracted"
        db.commit()
        return {"status": "already_done", "extracted": len(chunks)}

    total_chunks = len(chunks)
    sid = str(session.id)

    # Reset progress
    _extraction_progress[sid] = []
    _push_progress(sid, {"type": "started", "total_chunks": total_chunks, "pending": len(pending)})

    # Prepare chunk info before leaving this DB session
    chunk_infos = [
        (sid, c.id, c.chunk_index, total_chunks, c.start_turn, c.end_turn, c.overlap_start_turn, session.id)
        for c in pending
    ]

    session.status = "extracting"
    db.commit()

    # Launch parallel extraction in background
    max_workers = min(settings.max_parallel_extractions, len(pending))

    def _run_all():
        from archaeologist.db.session import SessionLocal
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_extract_one_chunk, *info) for info in chunk_infos]
            for f in futures:
                f.result()  # wait for all

        # Mark session as extracted
        db2 = SessionLocal()
        try:
            from archaeologist.db.models import Session
            s = db2.query(Session).filter(Session.id == chunk_infos[0][7]).first()
            if s:
                s.status = "extracted"
                db2.commit()
        finally:
            db2.close()

        _push_progress(sid, {"type": "all_done", "total_chunks": total_chunks})

    thread = threading.Thread(target=_run_all, daemon=True)
    thread.start()

    return {"status": "started", "total_chunks": total_chunks, "pending": len(pending), "workers": max_workers}


@router.get("/sessions/{session_id}/extract/progress")
async def extraction_progress_sse(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """SSE endpoint — streams extraction progress events."""
    session = _find_session(db, session_id)
    sid = str(session.id)

    async def event_stream():
        cursor = 0
        while True:
            if await request.is_disconnected():
                break

            events = _extraction_progress.get(sid, [])
            while cursor < len(events):
                evt = events[cursor]
                yield f"data: {json.dumps(evt)}\n\n"
                cursor += 1
                if evt.get("type") == "all_done":
                    return

            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _push_synthesis(session_id: str, event: dict):
    if session_id not in _synthesis_progress:
        _synthesis_progress[session_id] = []
    _synthesis_progress[session_id].append(event)


@router.post("/sessions/{session_id}/synthesize")
def trigger_synthesis(session_id: str, db: DBSession = Depends(get_db)):
    from archaeologist.db.models import Chunk

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
    session_id_uuid = session.id
    sid = str(session.id)

    _synthesis_progress[sid] = []
    _push_synthesis(sid, {"type": "started"})

    session.status = "synthesizing"
    db.commit()

    def _run():
        from sqlalchemy import func
        from archaeologist.db.models import Narrative, Session
        from archaeologist.db.session import SessionLocal
        from archaeologist.synthesizer.agent import synthesize_narrative

        def on_progress(evt):
            _push_synthesis(sid, {**evt, "type": "progress"})

        _push_synthesis(sid, {"type": "progress", "step": "calling_llm", "detail": "Calling Opus..."})
        narrative_md = synthesize_narrative(extractions, model=settings.synthesis_model, on_progress=on_progress)

        db2 = SessionLocal()
        try:
            max_rev = db2.query(func.max(Narrative.revision)).filter(Narrative.session_id == session_id_uuid).scalar()
            revision = (max_rev or 0) + 1

            narr = Narrative(
                session_id=session_id_uuid,
                revision=revision,
                content_md=narrative_md,
                synthesis_model=settings.synthesis_model,
            )
            db2.add(narr)
            s = db2.query(Session).filter(Session.id == session_id_uuid).first()
            if s:
                s.status = "synthesized"
            db2.commit()
            _push_synthesis(sid, {"type": "done", "revision": revision, "content_length": len(narrative_md)})
        finally:
            db2.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"status": "started"}


@router.get("/sessions/{session_id}/synthesize/progress")
async def synthesis_progress_sse(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """SSE endpoint — streams synthesis progress events."""
    session = _find_session(db, session_id)
    sid = str(session.id)

    async def event_stream():
        cursor = 0
        while True:
            if await request.is_disconnected():
                break

            events = _synthesis_progress.get(sid, [])
            while cursor < len(events):
                evt = events[cursor]
                yield f"data: {json.dumps(evt)}\n\n"
                cursor += 1
                if evt.get("type") == "done":
                    return

            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Full pipeline auto-run (chunk → extract → synthesize in one shot)
# ---------------------------------------------------------------------------
_pipeline_progress: dict[str, list[dict]] = {}


def _push_pipeline(sid: str, event: dict):
    if sid not in _pipeline_progress:
        _pipeline_progress[sid] = []
    _pipeline_progress[sid].append(event)


@router.post("/sessions/{session_id}/run-pipeline")
def run_pipeline(session_id: str, db: DBSession = Depends(get_db)):
    """Auto-run full pipeline: chunk → extract → synthesize. Returns immediately."""
    from archaeologist.db.models import Chunk

    session = _find_session(db, session_id)
    sid = str(session.id)
    session_uuid = session.id

    # Merge subagent turns into parent if applicable
    subagent_ids = []
    if session.session_type == "main":
        from archaeologist.db.models import Session as SessionModel
        subs = db.query(SessionModel).filter(SessionModel.parent_session_id == session.id).all()
        subagent_ids = [str(s.id) for s in subs]

    _pipeline_progress[sid] = []
    _push_pipeline(sid, {"type": "started"})

    def _run():
        from archaeologist.db.session import SessionLocal
        from archaeologist.db.models import Chunk, Turn, Narrative, Session as SM
        from archaeologist.chunker.engine import chunk_session
        from archaeologist.extractor.agent import extract_chunk
        from archaeologist.synthesizer.agent import synthesize_narrative
        from sqlalchemy import func
        from concurrent.futures import ThreadPoolExecutor
        import time

        db2 = SessionLocal()
        try:
            session = db2.query(SM).filter(SM.id == session_uuid).first()

            # --- Stage 1: Chunk ---
            _push_pipeline(sid, {"type": "stage", "stage": "chunk", "status": "running"})

            # Gather turns — main + subagent if applicable
            turns = list(db2.query(Turn).filter(Turn.session_id == session_uuid).order_by(Turn.turn_index).all())

            if subagent_ids:
                import uuid as _uuid
                for sa_id in subagent_ids:
                    sa_turns = db2.query(Turn).filter(
                        Turn.session_id == _uuid.UUID(sa_id)
                    ).order_by(Turn.turn_index).all()
                    turns.extend(sa_turns)
                # Re-sort by timestamp for chronological merge
                turns.sort(key=lambda t: t.timestamp or datetime(2000, 1, 1))
                # Re-index
                for i, t_obj in enumerate(turns):
                    pass  # keep original turn_index for DB reference

            turn_dicts = [
                {
                    "turn_index": i,
                    "token_estimate": t.token_estimate,
                    "timestamp": t.timestamp,
                    "role": t.role,
                    "is_compact_boundary": t.is_compact_boundary,
                    "is_error": t.is_error,
                    "tool_calls": t.tool_calls,
                    "content_text": t.content_text,
                }
                for i, t in enumerate(turns)
            ]

            chunks_data = chunk_session(turn_dicts, session.manifest or {})

            db2.query(Chunk).filter(Chunk.session_id == session_uuid).delete()
            chunk_records = []
            for cd in chunks_data:
                c = Chunk(
                    session_id=session_uuid,
                    chunk_index=cd["chunk_index"],
                    start_turn=cd["start_turn"],
                    end_turn=cd["end_turn"],
                    overlap_start_turn=cd.get("overlap_start_turn"),
                    token_estimate=cd["token_estimate"],
                    hot_zone_count=cd["hot_zone_count"],
                    contains_compact_boundary=cd["contains_compact_boundary"],
                )
                db2.add(c)
                chunk_records.append(c)
            session.status = "chunked"
            db2.commit()
            # Refresh to get IDs
            for c in chunk_records:
                db2.refresh(c)

            total_chunks = len(chunk_records)
            _push_pipeline(sid, {"type": "stage", "stage": "chunk", "status": "done", "chunks": total_chunks})

            # --- Stage 2: Extract (parallel) ---
            _push_pipeline(sid, {"type": "stage", "stage": "extract", "status": "running", "total": total_chunks})

            max_workers = min(settings.max_parallel_extractions, total_chunks)

            def extract_one(chunk_info):
                cid, cidx, start, end, overlap = chunk_info
                from archaeologist.db.session import SessionLocal as SL2
                db3 = SL2()
                try:
                    chunk_turns = turn_dicts[start:end + 1]
                    # Build pseudo-Turn objects for extractor
                    _push_pipeline(sid, {"type": "extract_chunk", "chunk": cidx + 1, "total": total_chunks, "status": "running"})
                    t0 = time.time()
                    result = extract_chunk(
                        turns=chunk_turns, chunk_id=cidx, total_chunks=total_chunks,
                        has_overlap=overlap is not None, overlap_tokens=0,
                        model=settings.extraction_model,
                    )
                    elapsed = time.time() - t0
                    c = db3.query(Chunk).filter(Chunk.id == cid).first()
                    if c:
                        c.extraction_result = result
                        c.extraction_status = "done"
                        c.extraction_model = settings.extraction_model
                        db3.commit()
                    _push_pipeline(sid, {"type": "extract_chunk", "chunk": cidx + 1, "total": total_chunks, "status": "done", "elapsed": round(elapsed, 1)})
                finally:
                    db3.close()

            chunk_infos = [(c.id, c.chunk_index, c.start_turn, c.end_turn, c.overlap_start_turn) for c in chunk_records]

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                list(pool.map(extract_one, chunk_infos))

            session = db2.query(SM).filter(SM.id == session_uuid).first()
            session.status = "extracted"
            db2.commit()
            _push_pipeline(sid, {"type": "stage", "stage": "extract", "status": "done"})

            # --- Stage 3: Synthesize ---
            _push_pipeline(sid, {"type": "stage", "stage": "synthesize", "status": "running"})

            chunks_done = db2.query(Chunk).filter(
                Chunk.session_id == session_uuid, Chunk.extraction_status == "done"
            ).order_by(Chunk.chunk_index).all()
            extractions = [c.extraction_result for c in chunks_done]

            def on_synth_progress(evt):
                _push_pipeline(sid, {"type": "synth_progress", **evt})

            narrative_md = synthesize_narrative(extractions, model=settings.synthesis_model, on_progress=on_synth_progress)

            max_rev = db2.query(func.max(Narrative.revision)).filter(Narrative.session_id == session_uuid).scalar()
            revision = (max_rev or 0) + 1
            narr = Narrative(
                session_id=session_uuid, revision=revision,
                content_md=narrative_md, synthesis_model=settings.synthesis_model,
            )
            db2.add(narr)
            session = db2.query(SM).filter(SM.id == session_uuid).first()
            session.status = "synthesized"
            db2.commit()

            _push_pipeline(sid, {"type": "stage", "stage": "synthesize", "status": "done", "revision": revision, "chars": len(narrative_md)})
            _push_pipeline(sid, {"type": "pipeline_done"})
        except Exception as e:
            _push_pipeline(sid, {"type": "error", "message": str(e)})
        finally:
            db2.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"status": "started", "subagents_merged": len(subagent_ids)}


@router.get("/sessions/{session_id}/run-pipeline/progress")
async def pipeline_progress_sse(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """SSE endpoint — streams full pipeline progress."""
    session = _find_session(db, session_id)
    sid = str(session.id)

    async def event_stream():
        cursor = 0
        while True:
            if await request.is_disconnected():
                break
            events = _pipeline_progress.get(sid, [])
            while cursor < len(events):
                evt = events[cursor]
                yield f"data: {json.dumps(evt)}\n\n"
                cursor += 1
                if evt.get("type") in ("pipeline_done", "error"):
                    return
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
