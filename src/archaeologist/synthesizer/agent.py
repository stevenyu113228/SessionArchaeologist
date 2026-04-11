"""Stage 4: Narrative synthesis agent — merge extractions into coherent narrative."""

from __future__ import annotations

import json
import logging

from archaeologist.llm.client import chat_completion
from archaeologist.synthesizer.prompts import SECTION_MERGE_SYSTEM, build_synthesis_system

logger = logging.getLogger(__name__)

# Conservative limit for Opus 200K context:
# ~150K input + system prompt, leaving room for output
MAX_SINGLE_CALL_TOKENS = 150_000
BATCH_SIZE = 8  # chunks per batch in hierarchical reduce


def synthesize_narrative(extractions: list[dict], model: str) -> str:
    """Synthesize chunk extractions into a research narrative.

    Uses single-call if extractions fit in context, otherwise
    hierarchical reduce (batch → section narratives → final merge).
    """
    total_chunks = len(extractions)
    serialized = _serialize_extractions(extractions)
    est_tokens = len(serialized) // 4  # rough estimate

    logger.info("Synthesis: %d chunks, ~%d tokens", total_chunks, est_tokens)

    if est_tokens <= MAX_SINGLE_CALL_TOKENS:
        return _single_call_synthesis(serialized, total_chunks, model)
    else:
        return _hierarchical_synthesis(extractions, model)


def _single_call_synthesis(serialized: str, total_chunks: int, model: str) -> str:
    """Single Opus call — all extractions fit in context."""
    system = build_synthesis_system(total_chunks)

    messages = [
        {
            "role": "user",
            "content": f"Here are the structured extraction notes from all {total_chunks} segments:\n\n{serialized}",
        }
    ]

    return chat_completion(
        messages=messages,
        model=model,
        system=system,
        max_tokens=16384,
        temperature=0.4,
    )


def _hierarchical_synthesis(extractions: list[dict], model: str) -> str:
    """Hierarchical reduce for large sessions.

    Step 1: Batch extractions into groups, synthesize each into a section narrative.
    Step 2: Merge all section narratives into the final document.
    """
    # Step 1: Batch synthesis
    section_narratives = []
    for batch_start in range(0, len(extractions), BATCH_SIZE):
        batch = extractions[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(extractions) + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info("Hierarchical step 1: batch %d/%d", batch_num, total_batches)

        serialized = _serialize_extractions(batch)
        system = build_synthesis_system(len(batch))
        system += (
            f"\n\nNote: This is batch {batch_num} of {total_batches}. "
            "Focus on the content in these segments — the final merge will combine all batches."
        )

        messages = [
            {
                "role": "user",
                "content": f"Extraction notes for segments {batch_start + 1}-{batch_start + len(batch)}:\n\n{serialized}",
            }
        ]

        section = chat_completion(
            messages=messages,
            model=model,
            system=system,
            max_tokens=8192,
            temperature=0.4,
        )
        section_narratives.append(section)

    # Step 2: Merge
    logger.info("Hierarchical step 2: merging %d sections", len(section_narratives))

    merge_system = SECTION_MERGE_SYSTEM.format(batch_count=len(section_narratives))
    combined = "\n\n" + "=" * 60 + "\n\n".join(
        f"### Section {i + 1}\n\n{s}" for i, s in enumerate(section_narratives)
    )

    messages = [
        {
            "role": "user",
            "content": f"Here are the section narratives to merge:\n{combined}",
        }
    ]

    return chat_completion(
        messages=messages,
        model=model,
        system=merge_system,
        max_tokens=16384,
        temperature=0.4,
    )


def _serialize_extractions(extractions: list[dict]) -> str:
    """Serialize extraction results for prompt inclusion."""
    parts = []
    for ext in extractions:
        chunk_id = ext.get("_chunk_id", "?")
        # Pretty-print with indentation for readability
        clean = {k: v for k, v in ext.items() if not k.startswith("_")}
        parts.append(f"### Chunk {chunk_id}\n```json\n{json.dumps(clean, indent=2, ensure_ascii=False)}\n```")
    return "\n\n".join(parts)
