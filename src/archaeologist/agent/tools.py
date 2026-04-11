"""Agent tool definitions and handler factory for session archaeology."""

from __future__ import annotations

import json
import re
from typing import Callable


# Tool definitions in Anthropic format
TOOL_SEARCH = {
    "name": "search_session",
    "description": (
        "Semantic search through raw session data (user messages, assistant responses, "
        "tool outputs, errors). Returns matching turns with content, role, turn_index, "
        "and relevance score. Use this to find specific technical details, error messages, "
        "commands, or code snippets from the original session."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query — be specific (e.g. 'SSH password sshpass error')"},
            "n_results": {"type": "integer", "description": "Number of results (default 10, max 20)"},
        },
        "required": ["query"],
    },
}

TOOL_READ_TURNS = {
    "name": "read_turns",
    "description": (
        "Read specific turns from the original session by index range. "
        "Use this when you know which turns contain relevant content "
        "(e.g. after finding turn indices from search results)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "start": {"type": "integer", "description": "Start turn index (inclusive)"},
            "end": {"type": "integer", "description": "End turn index (inclusive)"},
        },
        "required": ["start", "end"],
    },
}

TOOL_READ_SECTION = {
    "name": "read_section",
    "description": (
        "Read a specific section from the current narrative by heading text. "
        "Use this to see what's already written before making changes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "heading": {"type": "string", "description": "Heading text to find (partial match, case-insensitive)"},
        },
        "required": ["heading"],
    },
}

TOOL_LIST_SECTIONS = {
    "name": "list_sections",
    "description": "List all sections in the current narrative with their headings and approximate character counts.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

TOOL_GET_SESSION_INFO = {
    "name": "get_session_info",
    "description": "Get session metadata: total turns, time range, tool usage stats, hot zones, error count, subagent info.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOLS = [TOOL_SEARCH, TOOL_READ_TURNS, TOOL_READ_SECTION, TOOL_LIST_SECTIONS, TOOL_GET_SESSION_INFO]


def create_tool_handler(
    session_id: str,
    narrative_md: str = "",
    manifest: dict | None = None,
) -> Callable[[str, dict], str]:
    """Create a tool_handler function bound to a specific session context.

    Args:
        session_id: UUID string of the session.
        narrative_md: Current narrative markdown (for read_section/list_sections).
        manifest: Session manifest dict (for get_session_info).
    """

    def handler(tool_name: str, tool_input: dict) -> str:
        if tool_name == "search_session":
            return _handle_search(session_id, tool_input)
        elif tool_name == "read_turns":
            return _handle_read_turns(session_id, tool_input)
        elif tool_name == "read_section":
            return _handle_read_section(narrative_md, tool_input)
        elif tool_name == "list_sections":
            return _handle_list_sections(narrative_md)
        elif tool_name == "get_session_info":
            return _handle_session_info(manifest or {})
        else:
            return f"Unknown tool: {tool_name}"

    return handler


def _handle_search(session_id: str, params: dict) -> str:
    from archaeologist.rag.store import search

    query = params.get("query", "")
    n_results = min(params.get("n_results", 10), 20)

    results = search(session_id, query, mode="semantic", n_results=n_results)
    if not results:
        return "No results found."

    lines = []
    for r in results:
        lines.append(
            f"[Turn #{r['turn_index']}] [{r['role']}] (score: {r['score']:.2f})\n"
            f"{r['content_text'][:3000]}"
        )
    return "\n\n---\n\n".join(lines)


def _handle_read_turns(session_id: str, params: dict) -> str:
    from archaeologist.db.models import Turn
    from archaeologist.db.session import SessionLocal
    import uuid

    start = params.get("start", 0)
    end = params.get("end", start + 10)

    db = SessionLocal()
    try:
        turns = (
            db.query(Turn)
            .filter(
                Turn.session_id == uuid.UUID(session_id),
                Turn.turn_index >= start,
                Turn.turn_index <= end,
            )
            .order_by(Turn.turn_index)
            .limit(50)
            .all()
        )

        if not turns:
            return f"No turns found in range {start}-{end}."

        lines = []
        for t in turns:
            ts = f"[{t.timestamp}] " if t.timestamp else ""
            err = " [ERROR]" if t.is_error else ""
            lines.append(f"{ts}[#{t.turn_index}] [{t.role}]{err}\n{t.content_text[:5000]}")
        return "\n\n---\n\n".join(lines)
    finally:
        db.close()


def _handle_read_section(narrative_md: str, params: dict) -> str:
    heading = params.get("heading", "").lower()
    if not heading:
        return "Please provide a heading to search for."

    lines = narrative_md.split("\n")
    section_start = None
    section_level = None

    for i, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+)", line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()

            if section_start is None:
                if heading in text.lower():
                    section_start = i
                    section_level = level
            else:
                if level <= section_level:
                    return "\n".join(lines[section_start:i])

    if section_start is not None:
        return "\n".join(lines[section_start:])

    return f"Section not found: '{heading}'"


def _handle_list_sections(narrative_md: str) -> str:
    lines = narrative_md.split("\n")
    sections = []
    prev_start = 0

    for i, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+)", line)
        if match:
            if sections:
                sections[-1]["chars"] = sum(len(l) for l in lines[prev_start:i])
            sections.append({
                "level": len(match.group(1)),
                "heading": match.group(2).strip(),
                "line": i,
            })
            prev_start = i

    if sections:
        sections[-1]["chars"] = sum(len(l) for l in lines[prev_start:])

    if not sections:
        return "No sections found."

    result = []
    for s in sections:
        indent = "  " * (s["level"] - 1)
        result.append(f"{indent}{'#' * s['level']} {s['heading']} (~{s['chars']} chars)")
    return "\n".join(result)


def _handle_session_info(manifest: dict) -> str:
    info = {
        "total_turns": manifest.get("total_turns", 0),
        "total_tokens_est": manifest.get("total_tokens_est", 0),
        "time_range": manifest.get("time_range"),
        "error_count": manifest.get("error_count", 0),
        "hot_zones": len(manifest.get("hot_zones", [])),
        "compact_boundaries": len(manifest.get("compact_boundaries", [])),
        "tool_usage": manifest.get("tool_timeline", [])[:10],
        "role_distribution": manifest.get("role_distribution", {}),
    }
    return json.dumps(info, indent=2, ensure_ascii=False, default=str)
