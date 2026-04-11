"""Stage 4: Narrative synthesis agent — merge extractions into coherent narrative."""

from __future__ import annotations

import json
import logging
from typing import Callable

from archaeologist.llm.client import chat_completion
from archaeologist.synthesizer.prompts import (
    SECTION_MERGE_SYSTEM,
    SECTION_PROMPTS,
    build_synthesis_system,
)

logger = logging.getLogger(__name__)

MAX_SINGLE_CALL_TOKENS = 150_000
BATCH_SIZE = 8


def synthesize_narrative(
    extractions: list[dict],
    model: str,
    on_progress: Callable[[dict], None] | None = None,
) -> str:
    """Synthesize chunk extractions into a research narrative.

    Uses section-by-section synthesis for richer output.
    Falls back to single-call for very small sessions (1 chunk).
    """
    total_chunks = len(extractions)
    serialized = _serialize_extractions(extractions)
    est_tokens = len(serialized) // 4

    logger.info("Synthesis: %d chunks, ~%d tokens", total_chunks, est_tokens)

    if est_tokens <= MAX_SINGLE_CALL_TOKENS:
        return _section_by_section_synthesis(serialized, total_chunks, model, on_progress)
    else:
        return _hierarchical_then_sections(extractions, model, on_progress)


def _section_by_section_synthesis(
    serialized: str,
    total_chunks: int,
    model: str,
    on_progress: Callable[[dict], None] | None = None,
) -> str:
    """Generate each narrative section with a dedicated Opus call."""
    sections = list(SECTION_PROMPTS.items())
    total_sections = len(sections)
    parts = []

    for i, (key, spec) in enumerate(sections):
        logger.info("Section %d/%d: %s", i + 1, total_sections, key)
        if on_progress:
            on_progress({
                "step": "section",
                "section": key,
                "section_num": i + 1,
                "total_sections": total_sections,
                "detail": f"Writing section {i + 1}/{total_sections}: {spec['title']}...",
            })

        messages = [
            {
                "role": "user",
                "content": (
                    f"Here are structured extraction notes from {total_chunks} "
                    f"chronological session segments:\n\n{serialized}"
                ),
            }
        ]

        section_text = chat_completion(
            messages=messages,
            model=model,
            system=spec["system"],
            max_tokens=spec["max_tokens"],
            temperature=0.4,
        )
        parts.append(section_text)

    narrative = "\n\n---\n\n".join(parts)
    logger.info("Section-by-section synthesis complete: %d chars", len(narrative))
    return narrative


def _hierarchical_then_sections(
    extractions: list[dict],
    model: str,
    on_progress: Callable[[dict], None] | None = None,
) -> str:
    """For very large sessions: batch-reduce extractions first, then section synthesis."""
    total_batches = (len(extractions) + BATCH_SIZE - 1) // BATCH_SIZE

    # Step 1: Batch reduce
    reduced_parts = []
    for batch_start in range(0, len(extractions), BATCH_SIZE):
        batch = extractions[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1

        logger.info("Hierarchical reduce: batch %d/%d", batch_num, total_batches)
        if on_progress:
            on_progress({"step": "reduce", "batch": batch_num, "total_batches": total_batches,
                         "detail": f"Reducing batch {batch_num}/{total_batches}..."})

        serialized = _serialize_extractions(batch)
        system = build_synthesis_system(len(batch))
        system += (
            f"\n\nNote: This is batch {batch_num} of {total_batches}. "
            "Preserve ALL technical detail — commands, errors, code. Do not summarize."
        )

        messages = [
            {"role": "user", "content": f"Extraction notes for segments {batch_start + 1}-{batch_start + len(batch)}:\n\n{serialized}"}
        ]

        section = chat_completion(
            messages=messages, model=model, system=system,
            max_tokens=16384, temperature=0.4,
        )
        reduced_parts.append(section)

    # Step 2: Use reduced parts as input for section-by-section synthesis
    combined = "\n\n" + "=" * 60 + "\n\n".join(
        f"### Batch {i + 1}\n\n{s}" for i, s in enumerate(reduced_parts)
    )

    if on_progress:
        on_progress({"step": "sections", "detail": "Writing final sections..."})

    return _section_by_section_synthesis(combined, len(extractions), model, on_progress)


def _serialize_extractions(extractions: list[dict]) -> str:
    parts = []
    for ext in extractions:
        chunk_id = ext.get("_chunk_id", "?")
        clean = {k: v for k, v in ext.items() if not k.startswith("_")}
        parts.append(f"### Chunk {chunk_id}\n```json\n{json.dumps(clean, indent=2, ensure_ascii=False)}\n```")
    return "\n\n".join(parts)
