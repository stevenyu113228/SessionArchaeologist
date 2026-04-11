"""Stage 3: Chunk-level extraction agent."""

from __future__ import annotations

import logging

from archaeologist.extractor.prompts import build_extraction_system
from archaeologist.llm.client import chat_completion_json

logger = logging.getLogger(__name__)


def extract_chunk(
    turns: list,
    chunk_id: int,
    total_chunks: int,
    has_overlap: bool,
    overlap_tokens: int,
    model: str,
) -> dict:
    """Extract structured research notes from a chunk of turns.

    Args:
        turns: SQLAlchemy Turn objects for this chunk.
        chunk_id: 0-based chunk index.
        total_chunks: Total number of chunks.
        has_overlap: Whether this chunk has overlap with previous.
        overlap_tokens: Approximate overlap token count.
        model: Model to use for extraction.

    Returns:
        Extraction result dict matching the JSON schema in prompts.py.
    """
    system = build_extraction_system(chunk_id, total_chunks, has_overlap, overlap_tokens)

    # Build the conversation content from turns
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

        # Truncate very long turns to avoid blowing up context
        display_text = text[:8000] if text else ""
        if text and len(text) > 8000:
            display_text += f"\n... [truncated, {len(text)} chars total]"

        content_parts.append(f"{ts_str}[{role}]{error_str}{tools_str}\n{display_text}")

    conversation = "\n\n---\n\n".join(content_parts)

    messages = [{"role": "user", "content": f"Here is the session segment to analyze:\n\n{conversation}"}]

    result = chat_completion_json(
        messages=messages,
        model=model,
        system=system,
        max_tokens=8192,
        temperature=0.2,
    )

    # Add chunk metadata to result
    result["_chunk_id"] = chunk_id
    result["_model"] = model

    return result
