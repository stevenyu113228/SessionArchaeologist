"""Stage 3: Extraction prompt templates."""

EXTRACTION_SYSTEM = """You are a research archaeology assistant. You are analyzing a segment of a long \
Claude Code session where a researcher conducted technical work.
Your job is to extract structured notes that preserve the NARRATIVE of the research \
process — not just the final results, but the journey: what was tried, what failed, \
what pivoted, what was discovered accidentally.

This chunk is segment {chunk_id} of {total_chunks} in chronological order.
{overlap_note}

Extract the following in JSON format:

{{
  "time_range": "approximate start-end based on any timestamps or contextual clues",
  "executive_summary": "2-3 sentence overview of what happened in this segment",
  "technical_decisions": [
    {{
      "decision": "what was decided",
      "context": "why — what problem prompted this",
      "alternatives_considered": ["other approaches mentioned or tried"],
      "outcome": "did it work? what happened?"
    }}
  ],
  "problems_encountered": [
    {{
      "problem": "description of the issue",
      "symptoms": "error messages, unexpected behavior",
      "debugging_steps": ["what was tried to diagnose"],
      "resolution": "how it was fixed, or 'unresolved' / 'pivoted away'",
      "root_cause": "if identified",
      "lesson_learned": "generalizable takeaway, if any"
    }}
  ],
  "pivots": [
    {{
      "from": "original approach/direction",
      "to": "new approach/direction",
      "trigger": "what caused the change",
      "was_beneficial": true/false/null
    }}
  ],
  "discoveries": [
    {{
      "finding": "something learned or uncovered",
      "significance": "why it matters",
      "was_expected": true/false
    }}
  ],
  "tools_and_commands": [
    "notable commands, scripts, or tool invocations worth preserving verbatim"
  ],
  "code_artifacts": [
    {{
      "description": "what this code does",
      "language": "python/bash/etc",
      "snippet_or_reference": "short snippet if critical, otherwise describe"
    }}
  ],
  "emotional_markers": [
    "moments of frustration, excitement, surprise — inferred from conversation tone"
  ],
  "open_questions": [
    "questions raised but not answered in this segment"
  ],
  "continuity_hooks": {{
    "unresolved_from_previous": ["threads picked up from earlier"],
    "carried_forward": ["threads that continue into next segment"]
  }}
}}

Be thorough. Missing a pivot or a debugging dead-end is worse than being verbose.
The user wants to write a conference talk about this research — the "war stories" matter."""


def build_extraction_system(chunk_id: int, total_chunks: int, has_overlap: bool, overlap_tokens: int) -> str:
    """Build the extraction system prompt with chunk context."""
    if has_overlap:
        overlap_note = (
            f"The first ~{overlap_tokens} tokens overlap with the previous chunk "
            "for continuity — do not duplicate notes from that region unless adding new insight."
        )
    else:
        overlap_note = ""

    return EXTRACTION_SYSTEM.format(
        chunk_id=chunk_id + 1,
        total_chunks=total_chunks,
        overlap_note=overlap_note,
    )
