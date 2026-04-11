"""Export endpoints — multiple formats + template system."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from archaeologist.api.deps import get_db
from archaeologist.api.routes.sessions import _find_session
from archaeologist.db.models import Narrative

router = APIRouter()


class ExportRequest(BaseModel):
    format: str = "markdown"  # markdown, docx, slides, json
    template: str | None = None  # whitepaper, conference_talk, blog_post, internal_report
    revision: int = -1  # -1 for latest


@router.post("/{session_id}/export")
def export_narrative(session_id: str, req: ExportRequest, db: DBSession = Depends(get_db)):
    session = _find_session(db, session_id)

    if req.revision == -1:
        narr = db.query(Narrative).filter(
            Narrative.session_id == session.id
        ).order_by(Narrative.revision.desc()).first()
    else:
        narr = db.query(Narrative).filter(
            Narrative.session_id == session.id, Narrative.revision == req.revision
        ).first()

    if not narr:
        raise HTTPException(404, "No narrative found")

    content = narr.content_md

    # Apply template rewrite if requested
    if req.template:
        from archaeologist.export.templates import get_template_prompt
        from archaeologist.llm.client import chat_completion
        from archaeologist.config import settings

        system = get_template_prompt(req.template)
        content = chat_completion(
            messages=[{"role": "user", "content": content}],
            model=settings.synthesis_model,
            system=system,
            max_tokens=16384,
        )

    if req.format == "markdown":
        tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w")
        tmp.write(content)
        tmp.close()
        return FileResponse(
            tmp.name,
            media_type="text/markdown",
            filename=f"{session.name}-rev{narr.revision}.md",
        )

    elif req.format == "docx":
        from archaeologist.export.docx import markdown_to_docx

        tmp = Path(tempfile.mktemp(suffix=".docx"))
        markdown_to_docx(content, tmp, title=session.name)
        return FileResponse(
            str(tmp),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{session.name}-rev{narr.revision}.docx",
        )

    elif req.format == "slides":
        from archaeologist.export.slides import narrative_to_slide_outline

        outline = narrative_to_slide_outline(content)
        tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w")
        tmp.write(outline)
        tmp.close()
        return FileResponse(
            tmp.name,
            media_type="text/markdown",
            filename=f"{session.name}-slides-rev{narr.revision}.md",
        )

    elif req.format == "json":
        return {
            "session_name": session.name,
            "revision": narr.revision,
            "content_md": content,
            "synthesis_model": narr.synthesis_model,
            "created_at": narr.created_at.isoformat() if narr.created_at else None,
        }

    else:
        raise HTTPException(400, f"Unknown format: {req.format}")


@router.get("/templates")
def list_templates():
    from archaeologist.export.templates import list_templates
    return {"templates": list_templates()}
