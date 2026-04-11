"""Stage 5: Refinement agent — iterate on narrative using ReAct agent loop."""

from __future__ import annotations

import logging
import re

from archaeologist.agent.engine import run_agent
from archaeologist.agent.tools import ALL_TOOLS, create_tool_handler
from archaeologist.llm.client import chat_completion
from archaeologist.refiner.prompts import (
    ADD_SUBSECTION_SYSTEM,
    CORRECTION_SYSTEM,
    EXPAND_SYSTEM,
    NEEDS_DETAIL_SYSTEM,
    SHRINK_SYSTEM,
    TONE_CHANGE_SYSTEM,
)

logger = logging.getLogger(__name__)


def refine_narrative(
    current_narrative: str,
    annotations: list[dict],
    session_id: str,
    manifest: dict | None = None,
    model: str = "",
) -> str:
    """Apply user annotations to refine the narrative using ReAct agent loop."""
    narrative = current_narrative

    for ann in annotations:
        ann_type = ann.get("type", "correction")
        section_path = ann.get("section", "")
        content = ann.get("content", "")
        tone = ann.get("tone", "")

        logger.info("Processing %s annotation for section: %s", ann_type, section_path)

        # Auto mode: let agent figure out where to apply
        if not section_path or section_path == "auto":
            new_narrative = _apply_auto(
                narrative=narrative,
                ann_type=ann_type,
                content=content,
                tone=tone,
                session_id=session_id,
                manifest=manifest,
                model=model,
            )
            if new_narrative:
                narrative = new_narrative
            continue

        section_text = _find_section(narrative, section_path)
        if not section_text:
            logger.warning("Section not found: %s — applying to full narrative", section_path)
            section_text = narrative

        if ann_type in ("correction", "injection"):
            new_section = _apply_correction(section_text, content, model)
        elif ann_type == "needs_detail":
            new_section = _apply_with_agent(
                section_text=section_text,
                task_detail=f"The author says: {content}",
                system=NEEDS_DETAIL_SYSTEM,
                session_id=session_id,
                narrative=narrative,
                manifest=manifest,
                model=model,
            )
        elif ann_type == "add_subsection":
            new_subsection = _apply_with_agent(
                section_text=section_text,
                task_detail=f"Add a new subsection about: {content}",
                system=ADD_SUBSECTION_SYSTEM,
                session_id=session_id,
                narrative=narrative,
                manifest=manifest,
                model=model,
            )
            # Append subsection to end of section
            new_section = section_text.rstrip() + "\n\n" + new_subsection
        elif ann_type == "tone_change":
            new_section = _apply_tone_change(section_text, tone or "war_story", model)
        else:
            logger.warning("Unknown annotation type: %s", ann_type)
            continue

        if section_text == narrative:
            narrative = new_section
        else:
            narrative = narrative.replace(section_text, new_section, 1)

    return narrative


def _apply_auto(
    narrative: str,
    ann_type: str,
    content: str,
    tone: str,
    session_id: str,
    manifest: dict | None = None,
    model: str = "",
) -> str | None:
    """Auto mode: agent reads the narrative, decides where to apply the annotation, and returns the updated full narrative."""
    tool_handler = create_tool_handler(
        session_id=session_id,
        narrative_md=narrative,
        manifest=manifest,
    )

    type_instructions = {
        "correction": f"The author wants to correct something: \"{content}\"\nFind the relevant section and fix the factual error.",
        "injection": f"The author wants to add context: \"{content}\"\nFind where this context belongs and incorporate it naturally.",
        "needs_detail": f"The author says: \"{content}\"\nFind the section that needs more detail and use search_session to enrich it with evidence from source data.",
        "add_subsection": f"The author wants a new subsection about: \"{content}\"\nFind the best parent section, search for relevant source data, and write a new subsection.",
        "tone_change": f"The author wants to change tone to '{tone}' for the section most related to: \"{content}\"",
    }

    instruction = type_instructions.get(ann_type, f"Apply this annotation: {content}")

    system = (
        "You are editing a research narrative. The author has given you an instruction "
        "but did NOT specify which section to apply it to. You must:\n\n"
        "1. Use list_sections to see all sections\n"
        "2. Use read_section to read candidate sections\n"
        "3. Determine the best section to apply the change\n"
        "4. If the annotation type requires source data (needs_detail, add_subsection), "
        "use search_session to find evidence\n"
        "5. Output the COMPLETE updated narrative with the change applied\n\n"
        "Return the FULL narrative markdown (all sections, not just the changed one)."
    )

    task = (
        f"Annotation type: {ann_type}\n"
        f"Instruction: {instruction}\n\n"
        f"Current narrative ({len(narrative)} chars) is available via the tools. "
        "Use list_sections and read_section to explore it. "
        "Then output the complete updated narrative."
    )

    result = run_agent(
        task=task,
        tools=ALL_TOOLS,
        tool_handler=tool_handler,
        model=model,
        system=system,
        max_iterations=50,
    )

    # Agent should return the full narrative; if too short, it probably only returned a section
    if result and len(result) > len(narrative) * 0.3:
        return result
    logger.warning("Auto annotation result too short (%d chars vs %d), skipping", len(result), len(narrative))
    return None


def expand_section(
    narrative: str,
    section_path: str,
    session_id: str,
    manifest: dict | None = None,
    model: str = "",
) -> str:
    """Expand a section using agent loop with RAG search."""
    section_text = _find_section(narrative, section_path)
    if not section_text:
        return narrative

    new_section = _apply_with_agent(
        section_text=section_text,
        task_detail="Expand this section with more detail from the original session data.",
        system=EXPAND_SYSTEM,
        session_id=session_id,
        narrative=narrative,
        manifest=manifest,
        model=model,
    )
    return narrative.replace(section_text, new_section, 1)


def shrink_section(
    narrative: str,
    section_path: str,
    model: str = "",
) -> str:
    """Shrink a section (no RAG needed, one-shot)."""
    section_text = _find_section(narrative, section_path)
    if not section_text:
        return narrative

    messages = [{"role": "user", "content": f"Condense this section:\n\n{section_text}"}]
    new_section = chat_completion(
        messages=messages, model=model, system=SHRINK_SYSTEM,
        max_tokens=8192, temperature=0.3,
    )
    return narrative.replace(section_text, new_section, 1)


def _apply_with_agent(
    section_text: str,
    task_detail: str,
    system: str,
    session_id: str,
    narrative: str,
    manifest: dict | None,
    model: str,
) -> str:
    """Run a ReAct agent with tools for tasks that need RAG search."""
    tool_handler = create_tool_handler(
        session_id=session_id,
        narrative_md=narrative,
        manifest=manifest,
    )

    task = (
        f"Current section content:\n\n{section_text}\n\n"
        f"---\n\n{task_detail}\n\n"
        "Use the available tools to search the original session data for relevant evidence. "
        "Then produce the updated section content."
    )

    result = run_agent(
        task=task,
        tools=ALL_TOOLS,
        tool_handler=tool_handler,
        model=model,
        system=system,
        max_iterations=50,
    )
    return result


def _apply_correction(section_text: str, user_correction: str, model: str) -> str:
    messages = [
        {
            "role": "user",
            "content": f"Current section:\n\n{section_text}\n\nAuthor's correction/addition:\n\n{user_correction}",
        }
    ]
    return chat_completion(
        messages=messages, model=model, system=CORRECTION_SYSTEM,
        max_tokens=8192, temperature=0.3,
    )


def _apply_tone_change(section_text: str, tone: str, model: str) -> str:
    messages = [
        {"role": "user", "content": f"Rewrite this section in '{tone}' tone:\n\n{section_text}"},
    ]
    return chat_completion(
        messages=messages, model=model, system=TONE_CHANGE_SYSTEM,
        max_tokens=8192, temperature=0.4,
    )


def _find_section(narrative: str, section_path: str) -> str | None:
    if not section_path:
        return None

    parts = section_path.split(".")
    heading_term = parts[0].replace("_", " ")

    lines = narrative.split("\n")
    section_start = None
    section_end = None
    heading_level = None

    for i, line in enumerate(lines):
        heading_match = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip().lower()

            if section_start is None:
                if heading_term.lower() in text:
                    section_start = i
                    heading_level = level
            else:
                if level <= heading_level:
                    section_end = i
                    break

    if section_start is None:
        return None
    if section_end is None:
        section_end = len(lines)

    section_lines = lines[section_start:section_end]

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
