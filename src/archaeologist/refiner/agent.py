"""Stage 5: Refinement agent — iterate on narrative based on user feedback."""

from __future__ import annotations

import logging
import re

from archaeologist.llm.client import chat_completion
from archaeologist.refiner.prompts import CORRECTION_SYSTEM, NEEDS_DETAIL_SYSTEM, TONE_CHANGE_SYSTEM

logger = logging.getLogger(__name__)


def refine_narrative(
    current_narrative: str,
    annotations: list[dict],
    chunks: list,
    turns_by_chunk: dict[int, list],
    model: str,
) -> str:
    """Apply user annotations to refine the narrative.

    Processes each annotation and returns the updated narrative.
    """
    narrative = current_narrative

    for ann in annotations:
        ann_type = ann.get("type", "correction")
        section_path = ann.get("section", "")
        content = ann.get("content", "")
        tone = ann.get("tone", "")

        logger.info("Processing %s annotation for section: %s", ann_type, section_path)

        # Find the section in the narrative
        section_text = _find_section(narrative, section_path)
        if not section_text:
            logger.warning("Section not found: %s — applying to full narrative", section_path)
            section_text = narrative

        if ann_type in ("correction", "injection"):
            new_section = _apply_correction(section_text, content, model)
        elif ann_type == "needs_detail":
            raw_context = _gather_raw_context(section_path, chunks, turns_by_chunk)
            new_section = _apply_detail(section_text, content, raw_context, model)
        elif ann_type == "tone_change":
            new_section = _apply_tone_change(section_text, tone or "war_story", model)
        else:
            logger.warning("Unknown annotation type: %s", ann_type)
            continue

        # Replace section in narrative
        if section_text == narrative:
            narrative = new_section
        else:
            narrative = narrative.replace(section_text, new_section, 1)

    return narrative


def _find_section(narrative: str, section_path: str) -> str | None:
    """Find a section in the narrative by path (e.g., 'war_stories.item_1').

    Uses heading matching to find the relevant section.
    """
    if not section_path:
        return None

    # Convert section_path to search terms
    # e.g., "key_technical_journey.phase_2" → look for "Key Technical Journey" heading
    #        then "Phase 2" sub-heading
    parts = section_path.split(".")
    heading_term = parts[0].replace("_", " ")

    # Find the heading in markdown
    lines = narrative.split("\n")
    section_start = None
    section_end = None
    heading_level = None

    for i, line in enumerate(lines):
        # Match markdown headings
        heading_match = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip().lower()

            if section_start is None:
                # Looking for the start
                if heading_term.lower() in text:
                    section_start = i
                    heading_level = level
            else:
                # Looking for the end (next heading at same or higher level)
                if level <= heading_level:
                    section_end = i
                    break

    if section_start is None:
        return None

    if section_end is None:
        section_end = len(lines)

    section_lines = lines[section_start:section_end]

    # If there's a sub-path, try to narrow further
    if len(parts) > 1:
        sub_term = parts[1].replace("_", " ")
        sub_start = None
        sub_end = None
        for j, line in enumerate(section_lines):
            if sub_term.lower() in line.lower() and sub_start is None:
                sub_start = j
            elif sub_start is not None and re.match(r"^#{1,6}\s+", line):
                sub_end = j
                break
        if sub_start is not None:
            section_lines = section_lines[sub_start : sub_end or len(section_lines)]

    return "\n".join(section_lines)


def _apply_correction(section_text: str, user_correction: str, model: str) -> str:
    """Apply a user correction/injection to a narrative section."""
    messages = [
        {
            "role": "user",
            "content": (
                f"Current section:\n\n{section_text}\n\n"
                f"Author's correction/addition:\n\n{user_correction}"
            ),
        }
    ]
    return chat_completion(
        messages=messages,
        model=model,
        system=CORRECTION_SYSTEM,
        max_tokens=4096,
        temperature=0.3,
    )


def _apply_detail(section_text: str, user_note: str, raw_context: str, model: str) -> str:
    """Re-enrich a section with more detail from raw data."""
    messages = [
        {
            "role": "user",
            "content": (
                f"Current section:\n\n{section_text}\n\n"
                f"Author's note about what's missing:\n\n{user_note}\n\n"
                f"Relevant raw session data:\n\n{raw_context}"
            ),
        }
    ]
    return chat_completion(
        messages=messages,
        model=model,
        system=NEEDS_DETAIL_SYSTEM,
        max_tokens=8192,
        temperature=0.3,
    )


def _apply_tone_change(section_text: str, tone: str, model: str) -> str:
    """Rewrite a section in the requested tone."""
    messages = [
        {
            "role": "user",
            "content": f"Rewrite this section in '{tone}' tone:\n\n{section_text}",
        }
    ]
    return chat_completion(
        messages=messages,
        model=model,
        system=TONE_CHANGE_SYSTEM,
        max_tokens=4096,
        temperature=0.4,
    )


def _gather_raw_context(section_path: str, chunks: list, turns_by_chunk: dict[int, list]) -> str:
    """Gather raw turn data relevant to a section.

    For now, use a simple heuristic: return turns from the first few chunks.
    Phase 4 (RAG) will make this much more precise.
    """
    parts = []
    # Take turns from first 2 chunks as context (rough heuristic)
    for c in chunks[:2]:
        chunk_idx = c.chunk_index if hasattr(c, "chunk_index") else c.get("chunk_index", 0)
        chunk_turns = turns_by_chunk.get(chunk_idx, [])
        for turn in chunk_turns[:30]:  # limit per chunk
            text = turn.content_text if hasattr(turn, "content_text") else turn.get("content_text", "")
            role = turn.role if hasattr(turn, "role") else turn.get("role", "")
            parts.append(f"[{role}] {text[:2000]}")

    return "\n\n---\n\n".join(parts) if parts else "(No raw context available)"
