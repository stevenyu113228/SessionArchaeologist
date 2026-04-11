"""Stage 4: Narrative synthesis prompt templates."""

SYNTHESIS_SYSTEM = """You are helping a researcher reconstruct the complete narrative arc of a \
deep research project conducted over many Claude Code sessions. You have structured \
extraction notes from {total_chunks} chronological segments.

Your task: Synthesize these into a coherent research narrative document with the \
following structure:

## 1. Research Overview
- What was the research goal?
- What was the final outcome/finding?
- Timeline (start to end, major milestones)

## 2. Methodology Evolution
- How did the approach change over time?
- What was the initial plan vs what actually happened?

## 3. Key Technical Journey
For each major phase of the research, write a section that includes:
- What was being attempted
- What worked and what didn't
- Critical debugging moments (with enough technical detail to be educational)
- Pivots and their triggers

## 4. War Stories & Lessons Learned
- The most interesting failures and what they taught
- Unexpected discoveries
- Things that would be done differently in hindsight

## 5. Technical Artifacts
- Key tools, scripts, configurations that were developed
- Reusable techniques

## 6. Open Questions & Future Work
- Unresolved threads
- Natural extensions of the research

Write in a voice suitable for a technical conference talk or whitepaper.
Be specific — use actual error messages, command outputs, and code references \
from the notes. The audience is technical peers who would appreciate the \
debugging details and methodology, not just polished results.

Preserve the chronological flow — the reader should feel the progression \
of the research, including the dead ends."""


def build_synthesis_system(total_chunks: int) -> str:
    return SYNTHESIS_SYSTEM.format(total_chunks=total_chunks)


SECTION_MERGE_SYSTEM = """You are merging partial narrative sections into a complete document.

You have {batch_count} section summaries, each covering a portion of a research project.
Merge them into a single cohesive narrative, eliminating redundancy while preserving \
all unique insights, war stories, and technical details.

Maintain the same document structure:
1. Research Overview
2. Methodology Evolution
3. Key Technical Journey
4. War Stories & Lessons Learned
5. Technical Artifacts
6. Open Questions & Future Work

The output should read as a single, well-structured document — not a concatenation of sections."""
