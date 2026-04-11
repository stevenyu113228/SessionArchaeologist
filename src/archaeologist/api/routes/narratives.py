"""Narrative endpoints — revisions, refinement, diff."""

from __future__ import annotations

import difflib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.api.routes.sessions import _find_session
from archaeologist.db.models import Annotation, Narrative

router = APIRouter()


class NarrativeOut(BaseModel):
    id: str
    revision: int
    parent_revision: Optional[int] = None
    content_md: str
    synthesis_model: Optional[str] = None
    user_score: Optional[int] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class NarrativeListItem(BaseModel):
    id: str
    revision: int
    parent_revision: Optional[int] = None
    synthesis_model: Optional[str] = None
    user_score: Optional[int] = None
    content_length: int
    created_at: Optional[str] = None


@router.get("/{session_id}/narratives", response_model=list[NarrativeListItem])
def list_narratives(session_id: str, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    narrs = db.query(Narrative).filter(Narrative.session_id == session.id).order_by(Narrative.revision).all()
    return [
        NarrativeListItem(
            id=str(n.id),
            revision=n.revision,
            parent_revision=n.parent_revision,
            synthesis_model=n.synthesis_model,
            user_score=n.user_score,
            content_length=len(n.content_md),
            created_at=n.created_at.isoformat() if n.created_at else None,
        )
        for n in narrs
    ]


@router.get("/{session_id}/narratives/{revision}", response_model=NarrativeOut)
def get_narrative(session_id: str, revision: int, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")
    return NarrativeOut(
        id=str(narr.id),
        revision=narr.revision,
        parent_revision=narr.parent_revision,
        content_md=narr.content_md,
        synthesis_model=narr.synthesis_model,
        user_score=narr.user_score,
        created_at=narr.created_at.isoformat() if narr.created_at else None,
    )


class AnnotateRequest(BaseModel):
    section_path: str
    annotation_type: str  # correction, injection, needs_detail, tone_change
    content: str = ""
    tone: str = ""


@router.post("/{session_id}/narratives/{revision}/annotate")
def annotate_narrative(
    session_id: str, revision: int, req: AnnotateRequest, db: DBSession = Depends(get_db)
):
    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")

    ann = Annotation(
        narrative_id=narr.id,
        section_path=req.section_path,
        annotation_type=req.annotation_type,
        content=req.content,
    )
    db.add(ann)
    db.commit()
    return {"id": str(ann.id)}


class RefineRequest(BaseModel):
    annotations: list[AnnotateRequest]


@router.post("/{session_id}/narratives/{revision}/refine")
def refine_narrative(
    session_id: str, revision: int, req: RefineRequest, db: DBSession = Depends(get_db)
):
    from archaeologist.config import settings
    from archaeologist.refiner.agent import refine_narrative as do_refine

    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")

    annotations = [
        {"section": a.section_path, "type": a.annotation_type, "content": a.content, "tone": a.tone}
        for a in req.annotations
    ]

    new_md = do_refine(
        current_narrative=narr.content_md,
        annotations=annotations,
        session_id=str(session.id),
        manifest=session.manifest,
        model=settings.refinement_model,
    )

    max_rev = db.query(func.max(Narrative.revision)).filter(Narrative.session_id == session.id).scalar()
    new_revision = (max_rev or 0) + 1

    new_narr = Narrative(
        session_id=session.id,
        revision=new_revision,
        parent_revision=revision,
        content_md=new_md,
        synthesis_model=settings.refinement_model,
    )
    db.add(new_narr)
    db.flush()

    for ann_data in req.annotations:
        ann = Annotation(
            narrative_id=new_narr.id,
            section_path=ann_data.section_path,
            annotation_type=ann_data.annotation_type,
            content=ann_data.content,
        )
        db.add(ann)

    db.commit()

    return {"revision": new_revision, "content_length": len(new_md)}


class UpdateNarrativeRequest(BaseModel):
    content_md: str


@router.put("/{session_id}/narratives/{revision}")
def update_narrative(
    session_id: str, revision: int, req: UpdateNarrativeRequest, db: DBSession = Depends(get_db)
):
    """Direct edit of narrative content — creates a new revision."""
    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")

    max_rev = db.query(func.max(Narrative.revision)).filter(Narrative.session_id == session.id).scalar()
    new_revision = (max_rev or 0) + 1

    new_narr = Narrative(
        session_id=session.id,
        revision=new_revision,
        parent_revision=revision,
        content_md=req.content_md,
        synthesis_model="manual_edit",
    )
    db.add(new_narr)
    db.commit()
    return {"revision": new_revision, "content_length": len(req.content_md)}


class ScoreRequest(BaseModel):
    score: int


@router.post("/{session_id}/narratives/{revision}/score")
def score_narrative(
    session_id: str, revision: int, req: ScoreRequest, db: DBSession = Depends(get_db)
):
    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")
    narr.user_score = req.score
    db.commit()
    return {"revision": revision, "score": req.score}


@router.get("/{session_id}/narratives/diff/{rev1}/{rev2}")
def diff_narratives(session_id: str, rev1: int, rev2: int, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)
    n1 = db.query(Narrative).filter(Narrative.session_id == session.id, Narrative.revision == rev1).first()
    n2 = db.query(Narrative).filter(Narrative.session_id == session.id, Narrative.revision == rev2).first()

    if not n1 or not n2:
        raise HTTPException(404, "One or both revisions not found")

    diff = list(difflib.unified_diff(
        n1.content_md.splitlines(keepends=True),
        n2.content_md.splitlines(keepends=True),
        fromfile=f"rev {rev1}",
        tofile=f"rev {rev2}",
    ))
    return {"diff": "".join(diff), "rev1": rev1, "rev2": rev2}


class SectionRequest(BaseModel):
    section_path: str


@router.post("/{session_id}/narratives/{revision}/expand-section")
def expand_section_endpoint(
    session_id: str, revision: int, req: SectionRequest, db: DBSession = Depends(get_db)
):
    """Expand a section using agent loop with RAG search for evidence."""
    from archaeologist.config import settings
    from archaeologist.refiner.agent import expand_section

    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")

    new_md = expand_section(
        narrative=narr.content_md,
        section_path=req.section_path,
        session_id=str(session.id),
        manifest=session.manifest,
        model=settings.refinement_model,
    )

    return _save_new_revision(db, session, narr, new_md, "expand")


@router.post("/{session_id}/narratives/{revision}/shrink-section")
def shrink_section_endpoint(
    session_id: str, revision: int, req: SectionRequest, db: DBSession = Depends(get_db)
):
    """Shrink a section (one-shot, no RAG needed)."""
    from archaeologist.config import settings
    from archaeologist.refiner.agent import shrink_section

    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")

    new_md = shrink_section(
        narrative=narr.content_md,
        section_path=req.section_path,
        model=settings.refinement_model,
    )

    return _save_new_revision(db, session, narr, new_md, "shrink")


class TranslateRequest(BaseModel):
    target_lang: str = "zh-TW"


@router.post("/{session_id}/narratives/{revision}/translate")
def translate_narrative(
    session_id: str, revision: int, req: TranslateRequest, db: DBSession = Depends(get_db)
):
    """Translate narrative to target language using Sonnet (section by section)."""
    import re
    from archaeologist.config import settings
    from archaeologist.llm.client import chat_completion

    session = _find_session(db, session_id)
    narr = db.query(Narrative).filter(
        Narrative.session_id == session.id, Narrative.revision == revision
    ).first()
    if not narr:
        raise HTTPException(404, f"Revision {revision} not found")

    lang_names = {"zh-TW": "繁體中文", "en": "English", "ja": "日本語", "ko": "한국어"}
    lang_name = lang_names.get(req.target_lang, req.target_lang)

    # Split by ## headings for section-by-section translation
    sections = re.split(r"(?=^## )", narr.content_md, flags=re.MULTILINE)
    translated_parts = []

    system = (
        f"You are a professional translator. Translate the following markdown content to {lang_name}. "
        "Preserve all markdown formatting, code blocks, and technical terms. "
        "Translate prose naturally but keep variable names, function names, CLI commands, "
        "error messages, file paths, and code snippets in their original form."
    )

    for section in sections:
        if not section.strip():
            continue
        result = chat_completion(
            messages=[{"role": "user", "content": section}],
            model=settings.extraction_model,  # Sonnet for cost efficiency
            system=system,
            max_tokens=8192,
            temperature=0.2,
        )
        translated_parts.append(result)

    translated_md = "\n\n".join(translated_parts)
    return _save_new_revision(db, session, narr, translated_md, f"translate:{req.target_lang}")


def _save_new_revision(db, session, narr, new_md: str, model_tag: str) -> dict:
    """Helper to save a new narrative revision."""
    max_rev = db.query(func.max(Narrative.revision)).filter(Narrative.session_id == session.id).scalar()
    new_revision = (max_rev or 0) + 1

    new_narr = Narrative(
        session_id=session.id,
        revision=new_revision,
        parent_revision=narr.revision,
        content_md=new_md,
        synthesis_model=model_tag,
    )
    db.add(new_narr)
    db.commit()
    return {"revision": new_revision, "content_length": len(new_md)}
