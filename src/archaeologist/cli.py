"""SessionArchaeologist CLI — powered by Typer."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="archaeologist",
    help="Transform Claude Code session histories into research narratives.",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------
@app.command()
def ingest(
    path: Path = typer.Argument(..., help="Path to a .jsonl file or a Claude Code project directory"),
    preview: bool = typer.Option(False, "--preview", "-p", help="Preview parsed data without writing to DB"),
    name: str | None = typer.Option(None, "--name", "-n", help="Session name (auto-detected if omitted)"),
):
    """Stage 1: Parse and import a Claude Code JSONL session."""
    from archaeologist.parser.jsonl import parse_jsonl_file

    # Resolve files to parse
    files = _resolve_jsonl_files(path)
    if not files:
        rprint(f"[red]No .jsonl files found at {path}[/red]")
        raise typer.Exit(1)

    rprint(f"Found [cyan]{len(files)}[/cyan] JSONL file(s)")

    for file_path in files:
        rprint(f"\n[bold]Parsing:[/bold] {file_path}")
        turns, manifest = parse_jsonl_file(file_path)

        session_name = name or manifest.get("session_slug") or file_path.stem

        if preview:
            _show_preview(turns, manifest, session_name)
            continue

        # Store in DB
        session_id = _store_session(file_path, turns, manifest, session_name)
        rprint(f"[green]✓[/green] Imported as session [cyan]{session_id}[/cyan]")
        rprint(f"  {manifest['total_turns']} turns, ~{manifest['total_tokens_est']:,} tokens")
        if manifest["hot_zones"]:
            rprint(f"  [yellow]{len(manifest['hot_zones'])} hot zone(s)[/yellow] detected")
        if manifest["compact_boundaries"]:
            rprint(f"  [blue]{len(manifest['compact_boundaries'])} compact boundary(ies)[/blue]")
        if manifest["error_count"]:
            rprint(f"  [red]{manifest['error_count']} error(s)[/red]")


def _resolve_jsonl_files(path: Path) -> list[Path]:
    """Resolve path to list of .jsonl files."""
    if path.is_file() and path.suffix == ".jsonl":
        return [path]
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    return []


def _show_preview(turns: list[dict], manifest: dict, session_name: str):
    """Display a preview of parsed session data."""
    rprint(Panel(f"[bold]{session_name}[/bold]", title="Session Preview"))

    # Manifest stats
    table = Table(title="Manifest")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total turns", str(manifest["total_turns"]))
    table.add_row("Total tokens (est)", f"{manifest['total_tokens_est']:,}")
    table.add_row("Errors", str(manifest["error_count"]))
    table.add_row("Hot zones", str(len(manifest["hot_zones"])))
    table.add_row("Compact boundaries", str(len(manifest["compact_boundaries"])))
    table.add_row("Sidechains", str(manifest["sidechain_count"]))
    table.add_row("Thinking turns", str(manifest["thinking_count"]))
    if manifest["time_range"]:
        table.add_row("Time range", f"{manifest['time_range']['start']} → {manifest['time_range']['end']}")
        table.add_row("Duration", f"{manifest['time_range']['duration_hours']:.1f} hours")
    table.add_row("Parse errors", str(manifest["parse_errors"]))
    rprint(table)

    # Role distribution
    rprint("\n[bold]Role distribution:[/bold]")
    for role, count in manifest.get("role_distribution", {}).items():
        rprint(f"  {role}: {count}")

    # Tool usage
    if manifest.get("tool_timeline"):
        rprint("\n[bold]Top tools:[/bold]")
        for item in manifest["tool_timeline"][:10]:
            rprint(f"  {item['tool']}: {item['count']}")

    # Sample turns
    rprint(f"\n[bold]First 3 turns:[/bold]")
    for turn in turns[:3]:
        _print_turn_summary(turn)

    if len(turns) > 6:
        rprint(f"\n[dim]... ({len(turns) - 6} turns omitted) ...[/dim]")

    rprint(f"\n[bold]Last 3 turns:[/bold]")
    for turn in turns[-3:]:
        _print_turn_summary(turn)


def _print_turn_summary(turn: dict):
    role_color = {"user": "green", "assistant": "blue", "system": "yellow"}.get(turn["role"], "white")
    content_preview = turn["content_text"][:150].replace("\n", " ")
    if len(turn["content_text"]) > 150:
        content_preview += "..."
    tools_str = ""
    if turn["tool_calls"]:
        tools_str = f" [dim]tools: {', '.join(tc['tool_name'] for tc in turn['tool_calls'])}[/dim]"
    error_str = " [red]ERROR[/red]" if turn["is_error"] else ""
    rprint(
        f"  [{role_color}]#{turn['turn_index']} {turn['role']}[/{role_color}]"
        f"{error_str}{tools_str}: {content_preview}"
    )


def _store_session(file_path: Path, turns: list[dict], manifest: dict, session_name: str) -> str:
    """Store parsed session and turns in PostgreSQL."""
    from archaeologist.db.models import Session, Turn
    from archaeologist.db.session import SessionLocal

    db = SessionLocal()
    try:
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

        for turn_data in turns:
            turn = Turn(
                session_id=session.id,
                turn_index=turn_data["turn_index"],
                role=turn_data["role"],
                content_text=turn_data["content_text"],
                tool_calls=turn_data["tool_calls"],
                is_compact_boundary=turn_data["is_compact_boundary"],
                is_error=turn_data["is_error"],
                token_estimate=turn_data["token_estimate"],
                content_hash=turn_data["content_hash"],
                timestamp=turn_data["timestamp"],
                raw_jsonl_line=turn_data["raw_jsonl_line"],
                message_uuid=turn_data["message_uuid"],
                parent_uuid=turn_data["parent_uuid"],
                is_sidechain=turn_data["is_sidechain"],
                model_used=turn_data["model_used"],
                token_usage=turn_data["token_usage"],
                has_thinking=turn_data["has_thinking"],
            )
            db.add(turn)

        db.commit()
        return str(session.id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# sessions (list)
# ---------------------------------------------------------------------------
@app.command()
def sessions():
    """List all imported sessions."""
    from archaeologist.db.models import Session
    from archaeologist.db.session import SessionLocal

    db = SessionLocal()
    try:
        all_sessions = db.query(Session).order_by(Session.imported_at.desc()).all()
        if not all_sessions:
            rprint("[dim]No sessions found. Use 'archaeologist ingest' to import one.[/dim]")
            return

        table = Table(title="Sessions")
        table.add_column("ID", style="cyan", max_width=8)
        table.add_column("Name", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Turns", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Imported", style="dim")

        for s in all_sessions:
            table.add_row(
                str(s.id)[:8],
                s.name,
                s.status,
                str(s.total_turns),
                f"{s.total_tokens_est:,}",
                s.imported_at.strftime("%Y-%m-%d %H:%M") if s.imported_at else "",
            )
        rprint(table)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# chunk
# ---------------------------------------------------------------------------
@app.command()
def chunk(
    session_id: str = typer.Argument(..., help="Session ID (or prefix)"),
):
    """Stage 2: Split session into intelligent chunks."""
    from archaeologist.chunker.engine import chunk_session
    from archaeologist.db.models import Chunk, Session, Turn
    from archaeologist.db.session import SessionLocal

    db = SessionLocal()
    try:
        session = _resolve_session(db, session_id)
        turns = db.query(Turn).filter(Turn.session_id == session.id).order_by(Turn.turn_index).all()

        if not turns:
            rprint("[red]No turns found for this session.[/red]")
            raise typer.Exit(1)

        rprint(f"Chunking session [cyan]{session.name}[/cyan] ({len(turns)} turns)...")

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

        # Delete existing chunks for this session
        db.query(Chunk).filter(Chunk.session_id == session.id).delete()

        for chunk_data in chunks:
            c = Chunk(
                session_id=session.id,
                chunk_index=chunk_data["chunk_index"],
                start_turn=chunk_data["start_turn"],
                end_turn=chunk_data["end_turn"],
                overlap_start_turn=chunk_data.get("overlap_start_turn"),
                token_estimate=chunk_data["token_estimate"],
                hot_zone_count=chunk_data["hot_zone_count"],
                contains_compact_boundary=chunk_data["contains_compact_boundary"],
            )
            db.add(c)

        session.status = "chunked"
        db.commit()

        rprint(f"[green]✓[/green] Created [cyan]{len(chunks)}[/cyan] chunks")
        for c in chunks:
            hz = f" [yellow]🔥 {c['hot_zone_count']} hot zone(s)[/yellow]" if c["hot_zone_count"] else ""
            cb = " [blue]📦 compact[/blue]" if c["contains_compact_boundary"] else ""
            rprint(
                f"  Chunk {c['chunk_index']}: turns {c['start_turn']}-{c['end_turn']}"
                f" (~{c['token_estimate']:,} tokens){hz}{cb}"
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------
@app.command()
def extract(
    session_id: str = typer.Argument(..., help="Session ID (or prefix)"),
    model: str | None = typer.Option(None, "--model", "-m", help="Override extraction model"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show cost estimate without calling API"),
    chunk_id: str | None = typer.Option(None, "--chunk", "-c", help="Extract only this chunk"),
):
    """Stage 3: Extract structured notes from chunks via LLM."""
    from archaeologist.db.models import Chunk, Session, Turn
    from archaeologist.db.session import SessionLocal
    from archaeologist.config import settings
    from archaeologist.extractor.agent import extract_chunk

    db = SessionLocal()
    try:
        session = _resolve_session(db, session_id)
        use_model = model or settings.extraction_model

        if chunk_id:
            chunks_q = db.query(Chunk).filter(Chunk.session_id == session.id, Chunk.id == chunk_id)
        else:
            chunks_q = db.query(Chunk).filter(Chunk.session_id == session.id).order_by(Chunk.chunk_index)

        chunks = chunks_q.all()
        if not chunks:
            rprint("[red]No chunks found. Run 'archaeologist chunk' first.[/red]")
            raise typer.Exit(1)

        total_tokens = sum(c.token_estimate for c in chunks)
        est_cost = _estimate_cost(total_tokens, use_model)

        rprint(f"[bold]Extraction plan:[/bold]")
        rprint(f"  Session: [cyan]{session.name}[/cyan]")
        rprint(f"  Chunks: {len(chunks)}")
        rprint(f"  Total input tokens: ~{total_tokens:,}")
        rprint(f"  Model: {use_model}")
        rprint(f"  Estimated cost: [yellow]${est_cost:.2f}[/yellow]")

        if dry_run:
            rprint("[dim]Dry run — no API calls made.[/dim]")
            return

        if est_cost > settings.cost_confirmation_threshold:
            confirm = typer.confirm(f"Estimated cost ${est_cost:.2f} exceeds threshold. Continue?")
            if not confirm:
                raise typer.Abort()

        total_chunks = db.query(Chunk).filter(Chunk.session_id == session.id).count()

        for c in chunks:
            rprint(f"\n  Extracting chunk {c.chunk_index}...")
            turns = (
                db.query(Turn)
                .filter(
                    Turn.session_id == session.id,
                    Turn.turn_index >= c.start_turn,
                    Turn.turn_index <= c.end_turn,
                )
                .order_by(Turn.turn_index)
                .all()
            )

            has_overlap = c.overlap_start_turn is not None
            overlap_tokens = 0
            if has_overlap:
                overlap_turns = [t for t in turns if t.turn_index < c.start_turn]
                overlap_tokens = sum(t.token_estimate for t in overlap_turns)

            result = extract_chunk(
                turns=turns,
                chunk_id=c.chunk_index,
                total_chunks=total_chunks,
                has_overlap=has_overlap,
                overlap_tokens=overlap_tokens,
                model=use_model,
            )

            c.extraction_result = result
            c.extraction_status = "done"
            c.extraction_model = use_model
            db.commit()
            rprint(f"  [green]✓[/green] Chunk {c.chunk_index} extracted")

        session.status = "extracted"
        db.commit()
        rprint(f"\n[green]✓ Extraction complete[/green]")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# synthesize
# ---------------------------------------------------------------------------
@app.command()
def synthesize(
    session_id: str = typer.Argument(..., help="Session ID (or prefix)"),
    model: str | None = typer.Option(None, "--model", "-m", help="Override synthesis model"),
):
    """Stage 4: Synthesize extraction results into a research narrative."""
    from archaeologist.db.models import Chunk, Narrative, Session
    from archaeologist.db.session import SessionLocal
    from archaeologist.config import settings
    from archaeologist.synthesizer.agent import synthesize_narrative

    db = SessionLocal()
    try:
        session = _resolve_session(db, session_id)
        use_model = model or settings.synthesis_model

        chunks = (
            db.query(Chunk)
            .filter(Chunk.session_id == session.id, Chunk.extraction_status == "done")
            .order_by(Chunk.chunk_index)
            .all()
        )

        if not chunks:
            rprint("[red]No extracted chunks. Run 'archaeologist extract' first.[/red]")
            raise typer.Exit(1)

        rprint(f"Synthesizing narrative from [cyan]{len(chunks)}[/cyan] chunks using {use_model}...")

        extractions = [c.extraction_result for c in chunks]
        narrative_md = synthesize_narrative(extractions, model=use_model)

        # Determine revision number
        from sqlalchemy import func

        max_rev = db.query(func.max(Narrative.revision)).filter(Narrative.session_id == session.id).scalar()
        revision = (max_rev or 0) + 1

        narrative = Narrative(
            session_id=session.id,
            revision=revision,
            content_md=narrative_md,
            synthesis_model=use_model,
        )
        db.add(narrative)
        session.status = "synthesized"
        db.commit()

        rprint(f"[green]✓[/green] Narrative revision {revision} created ({len(narrative_md):,} chars)")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# refine
# ---------------------------------------------------------------------------
@app.command()
def refine(
    session_id: str = typer.Argument(..., help="Session ID (or prefix)"),
    feedback: Path = typer.Option(..., "--feedback", "-f", help="Path to feedback YAML file"),
    model: str | None = typer.Option(None, "--model", "-m", help="Override refinement model"),
):
    """Stage 5: Refine narrative based on user feedback."""
    from archaeologist.db.models import Annotation, Chunk, Narrative, Session, Turn
    from archaeologist.db.session import SessionLocal
    from archaeologist.config import settings
    from archaeologist.refiner.agent import refine_narrative
    from archaeologist.refiner.feedback import parse_feedback

    db = SessionLocal()
    try:
        session = _resolve_session(db, session_id)
        use_model = model or settings.refinement_model

        # Get latest narrative
        latest = (
            db.query(Narrative)
            .filter(Narrative.session_id == session.id)
            .order_by(Narrative.revision.desc())
            .first()
        )
        if not latest:
            rprint("[red]No narrative found. Run 'archaeologist synthesize' first.[/red]")
            raise typer.Exit(1)

        # Parse feedback
        annotations = parse_feedback(feedback)
        rprint(f"Loaded [cyan]{len(annotations)}[/cyan] annotations from {feedback}")

        # Get chunks for re-extraction if needed
        chunks = (
            db.query(Chunk)
            .filter(Chunk.session_id == session.id)
            .order_by(Chunk.chunk_index)
            .all()
        )

        # Get turns for detail retrieval
        turns_by_chunk: dict[int, list] = {}
        for c in chunks:
            chunk_turns = (
                db.query(Turn)
                .filter(
                    Turn.session_id == session.id,
                    Turn.turn_index >= c.start_turn,
                    Turn.turn_index <= c.end_turn,
                )
                .order_by(Turn.turn_index)
                .all()
            )
            turns_by_chunk[c.chunk_index] = chunk_turns

        rprint(f"Refining with model {use_model}...")
        new_narrative_md = refine_narrative(
            current_narrative=latest.content_md,
            annotations=annotations,
            chunks=chunks,
            turns_by_chunk=turns_by_chunk,
            model=use_model,
        )

        # Store new revision
        from sqlalchemy import func

        max_rev = db.query(func.max(Narrative.revision)).filter(Narrative.session_id == session.id).scalar()
        new_revision = (max_rev or 0) + 1

        new_narrative = Narrative(
            session_id=session.id,
            revision=new_revision,
            parent_revision=latest.revision,
            content_md=new_narrative_md,
            synthesis_model=use_model,
            annotations_data=[a.dict() if hasattr(a, "dict") else a for a in annotations],
        )
        db.add(new_narrative)
        db.flush()  # Generate new_narrative.id before creating annotations

        # Store annotations
        for ann in annotations:
            a = Annotation(
                narrative_id=new_narrative.id,
                section_path=ann.get("section", ""),
                annotation_type=ann.get("type", "correction"),
                content=ann.get("content", ""),
            )
            db.add(a)

        session.status = "refining"
        db.commit()

        # Show diff
        _show_diff(latest.content_md, new_narrative_md, latest.revision, new_revision)
        rprint(f"\n[green]✓[/green] Revision {new_revision} created")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------
@app.command()
def diff(
    session_id: str = typer.Argument(..., help="Session ID (or prefix)"),
    rev1: int = typer.Argument(..., help="First revision number"),
    rev2: int = typer.Argument(..., help="Second revision number"),
):
    """Compare two narrative revisions."""
    from archaeologist.db.models import Narrative
    from archaeologist.db.session import SessionLocal

    db = SessionLocal()
    try:
        session = _resolve_session(db, session_id)
        n1 = db.query(Narrative).filter(Narrative.session_id == session.id, Narrative.revision == rev1).first()
        n2 = db.query(Narrative).filter(Narrative.session_id == session.id, Narrative.revision == rev2).first()

        if not n1 or not n2:
            rprint("[red]One or both revisions not found.[/red]")
            raise typer.Exit(1)

        _show_diff(n1.content_md, n2.content_md, rev1, rev2)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# revisions
# ---------------------------------------------------------------------------
@app.command()
def revisions(
    session_id: str = typer.Argument(..., help="Session ID (or prefix)"),
):
    """List all narrative revisions for a session."""
    from archaeologist.db.models import Narrative
    from archaeologist.db.session import SessionLocal

    db = SessionLocal()
    try:
        session = _resolve_session(db, session_id)
        narrs = (
            db.query(Narrative).filter(Narrative.session_id == session.id).order_by(Narrative.revision).all()
        )

        if not narrs:
            rprint("[dim]No narratives found.[/dim]")
            return

        table = Table(title=f"Revisions for {session.name}")
        table.add_column("Rev", style="cyan", justify="right")
        table.add_column("Parent", justify="right")
        table.add_column("Model", style="dim")
        table.add_column("Score", justify="right")
        table.add_column("Length", justify="right")
        table.add_column("Created", style="dim")

        for n in narrs:
            table.add_row(
                str(n.revision),
                str(n.parent_revision or "-"),
                n.synthesis_model or "",
                str(n.user_score) if n.user_score else "-",
                f"{len(n.content_md):,}",
                n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
            )
        rprint(table)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
@app.command(name="export")
def export_cmd(
    session_id: str = typer.Argument(..., help="Session ID (or prefix)"),
    revision: int = typer.Option(-1, "--revision", "-r", help="Revision number (-1 for latest)"),
    output_dir: Path = typer.Option(Path("output"), "--output", "-o", help="Output directory"),
):
    """Export a narrative revision as Markdown."""
    from archaeologist.db.models import Narrative, Session
    from archaeologist.db.session import SessionLocal

    db = SessionLocal()
    try:
        session = _resolve_session(db, session_id)

        if revision == -1:
            narr = (
                db.query(Narrative)
                .filter(Narrative.session_id == session.id)
                .order_by(Narrative.revision.desc())
                .first()
            )
        else:
            narr = (
                db.query(Narrative)
                .filter(Narrative.session_id == session.id, Narrative.revision == revision)
                .first()
            )

        if not narr:
            rprint("[red]No narrative found.[/red]")
            raise typer.Exit(1)

        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{session.name}-rev{narr.revision}.md"
        out_path = output_dir / filename

        out_path.write_text(narr.content_md, encoding="utf-8")
        rprint(f"[green]✓[/green] Exported to [cyan]{out_path}[/cyan]")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# run (full pipeline)
# ---------------------------------------------------------------------------
@app.command()
def run(
    path: Path = typer.Argument(..., help="Path to JSONL file or directory"),
    through: str = typer.Option("export", "--through", "-t", help="Stop after: chunk|extract|synthesize|export"),
    name: str | None = typer.Option(None, "--name", "-n", help="Session name"),
):
    """Run the full pipeline: ingest → chunk → extract → synthesize → export."""
    from archaeologist.db.models import Session as SessionModel
    from archaeologist.db.session import SessionLocal

    stages = ["ingest", "chunk", "extract", "synthesize", "export"]
    if through not in stages[1:]:
        rprint(f"[red]--through must be one of: {', '.join(stages[1:])}[/red]")
        raise typer.Exit(1)

    stop_idx = stages.index(through)

    # Stage 1: Ingest
    rprint("\n[bold]━━━ Stage 1: Ingest ━━━[/bold]")
    from archaeologist.parser.jsonl import parse_jsonl_file

    files = _resolve_jsonl_files(path)
    if not files:
        rprint(f"[red]No .jsonl files found at {path}[/red]")
        raise typer.Exit(1)

    # For pipeline, process first file
    file_path = files[0]
    if len(files) > 1:
        rprint(f"[yellow]Multiple files found, processing first: {file_path}[/yellow]")

    turns, manifest = parse_jsonl_file(file_path)
    session_name = name or manifest.get("session_slug") or file_path.stem
    session_id = _store_session(file_path, turns, manifest, session_name)
    rprint(f"[green]✓[/green] Ingested: {manifest['total_turns']} turns, ~{manifest['total_tokens_est']:,} tokens")

    if stop_idx < 1:
        return

    # Stage 2: Chunk
    rprint("\n[bold]━━━ Stage 2: Chunk ━━━[/bold]")
    # Invoke chunk command logic directly
    from typer.testing import CliRunner

    chunk(session_id=session_id)

    if stop_idx < 2:
        return

    # Stage 3: Extract
    rprint("\n[bold]━━━ Stage 3: Extract ━━━[/bold]")
    extract(session_id=session_id, model=None, dry_run=False, chunk_id=None)

    if stop_idx < 3:
        return

    # Stage 4: Synthesize
    rprint("\n[bold]━━━ Stage 4: Synthesize ━━━[/bold]")
    synthesize(session_id=session_id, model=None)

    if stop_idx < 4:
        return

    # Stage 5: Export
    rprint("\n[bold]━━━ Stage 5: Export ━━━[/bold]")
    export_cmd(session_id=session_id, revision=-1, output_dir=Path("output"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_session(db, session_id_prefix: str):
    """Find a session by ID or prefix."""
    from archaeologist.db.models import Session

    # Try exact match
    try:
        uid = uuid.UUID(session_id_prefix)
        session = db.query(Session).filter(Session.id == uid).first()
        if session:
            return session
    except ValueError:
        pass

    # Try prefix match
    session = db.query(Session).filter(Session.id.cast(String).startswith(session_id_prefix)).first()
    if session:
        return session

    # Try name match
    session = db.query(Session).filter(Session.name.ilike(f"%{session_id_prefix}%")).first()
    if session:
        return session

    rprint(f"[red]Session not found: {session_id_prefix}[/red]")
    raise typer.Exit(1)


def _estimate_cost(tokens: int, model: str) -> float:
    """Rough cost estimate based on model and tokens."""
    # Approximate rates per 1M tokens (input)
    rates = {
        "claude-4.6-sonnet": 3.0,
        "claude-4.6-opus": 15.0,
        "claude-4.5-sonnet": 3.0,
        "claude-4.5-opus": 15.0,
    }
    rate = rates.get(model, 5.0)
    return (tokens / 1_000_000) * rate


def _show_diff(text1: str, text2: str, rev1: int, rev2: int):
    """Show unified diff between two texts."""
    import difflib

    lines1 = text1.splitlines(keepends=True)
    lines2 = text2.splitlines(keepends=True)
    diff = difflib.unified_diff(lines1, lines2, fromfile=f"rev {rev1}", tofile=f"rev {rev2}")

    has_diff = False
    for line in diff:
        has_diff = True
        if line.startswith("+") and not line.startswith("+++"):
            rprint(f"[green]{line.rstrip()}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            rprint(f"[red]{line.rstrip()}[/red]")
        elif line.startswith("@@"):
            rprint(f"[cyan]{line.rstrip()}[/cyan]")
        else:
            rprint(line.rstrip())

    if not has_diff:
        rprint("[dim]No differences.[/dim]")


# Need String import for prefix match
from sqlalchemy import String

if __name__ == "__main__":
    app()
