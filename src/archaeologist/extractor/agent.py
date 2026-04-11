"""Stage 3: Chunk-level extraction agent."""

from __future__ import annotations

import logging

from archaeologist.extractor.prompts import build_extraction_system
from archaeologist.llm.client import chat_completion, chat_completion_json

logger = logging.getLogger(__name__)

TURN_DISPLAY_LIMIT = 20000  # chars per turn (raised from 8000)


def extract_chunk(
    turns: list,
    chunk_id: int,
    total_chunks: int,
    has_overlap: bool,
    overlap_tokens: int,
    model: str,
) -> dict:
    """Extract structured research notes from a chunk of turns."""
    system = build_extraction_system(chunk_id, total_chunks, has_overlap, overlap_tokens)
    conversation = _build_conversation(turns)

    messages = [{"role": "user", "content": f"Here is the session segment to analyze:\n\n{conversation}"}]

    result = chat_completion_json(
        messages=messages,
        model=model,
        system=system,
        max_tokens=16384,  # raised from 8192
        temperature=0.2,
    )

    result["_chunk_id"] = chunk_id
    result["_model"] = model
    return result


def extract_artifacts(
    turns: list,
    chunk_id: int,
    model: str,
) -> dict:
    """Second-pass extraction: capture all code, commands, errors verbatim."""
    conversation = _build_conversation(turns)

    system = (
        "You are extracting technical artifacts from a session segment. "
        "Extract ALL of the following VERBATIM — do not summarize or paraphrase:\n\n"
        "1. Bash/shell commands that were executed\n"
        "2. Code snippets that were written or modified (include language)\n"
        "3. Error messages and tracebacks (complete, not truncated)\n"
        "4. Configuration files and their contents\n"
        "5. SQL queries\n"
        "6. API requests/responses\n"
        "7. File paths that were referenced\n\n"
        "For each artifact, include:\n"
        "- The artifact itself (verbatim)\n"
        "- Brief context: what was it for, did it work\n\n"
        "Respond in JSON: {\"artifacts\": [{\"type\": \"command|code|error|config|sql|api|path\", "
        "\"content\": \"verbatim content\", \"context\": \"brief explanation\", \"language\": \"bash|python|...\"}]}\n\n"
        "Be thorough. Missing an artifact is worse than including too many."
    )

    messages = [{"role": "user", "content": f"Session segment:\n\n{conversation}"}]

    result = chat_completion_json(
        messages=messages,
        model=model,
        system=system,
        max_tokens=16384,
        temperature=0.1,
    )
    return result


def _build_conversation(turns: list) -> str:
    """Build conversation text from turns for LLM consumption."""
    content_parts = []
    for turn in turns:
        role = turn.role if hasattr(turn, "role") else turn["role"]
        text = turn.content_text if hasattr(turn, "content_text") else turn["content_text"]
        timestamp = turn.timestamp if hasattr(turn, "timestamp") else turn.get("timestamp")
        tool_calls = turn.tool_calls if hasattr(turn, "tool_calls") else turn.get("tool_calls")
        is_error = turn.is_error if hasattr(turn, "is_error") else turn.get("is_error", False)

        ts_str = f"[{timestamp}] " if timestamp else ""
        error_str = " [ERROR]" if is_error else ""

        if tool_calls:
            tools_str = " | tools: " + ", ".join(
                f"{tc['tool_name']}({tc.get('input_summary', '')[:80]})" for tc in tool_calls
            )
        else:
            tools_str = ""

        display_text = text[:TURN_DISPLAY_LIMIT] if text else ""
        if text and len(text) > TURN_DISPLAY_LIMIT:
            display_text += f"\n... [truncated, {len(text)} chars total]"

        content_parts.append(f"{ts_str}[{role}]{error_str}{tools_str}\n{display_text}")

    return "\n\n---\n\n".join(content_parts)
