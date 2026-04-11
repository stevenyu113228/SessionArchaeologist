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


# Per-section prompts for section-by-section synthesis
SECTION_PROMPTS = {
    "research_overview": {
        "title": "## 1. Research Overview",
        "max_tokens": 8192,
        "system": """You are writing the "Research Overview" section of a research narrative.

Based on the extraction notes provided, write a comprehensive overview covering:
- **Goal**: What was the research/project goal?
- **Final Outcome**: What were the concrete results?
- **Timeline**: A detailed timeline table with dates and milestones

Be specific and detailed. Include actual dates, tool names, and quantitative results.
Write ONLY this section — no other sections. Start with "## 1. Research Overview".""",
    },
    "methodology": {
        "title": "## 2. Methodology Evolution",
        "max_tokens": 8192,
        "system": """You are writing the "Methodology Evolution" section of a research narrative.

Based on the extraction notes, write about how the approach changed over time:
- What was the initial plan?
- How did reality differ from the plan?
- What pivots happened and why?
- How did the methodology evolve layer by layer?

Be specific about what triggered each change. Include actual error messages or discoveries that caused pivots.
Write ONLY this section. Start with "## 2. Methodology Evolution".""",
    },
    "technical_journey": {
        "title": "## 3. Key Technical Journey",
        "max_tokens": 16384,
        "system": """You are writing the "Key Technical Journey" section — the MAIN section of a research narrative.

For each major phase of the research, write a detailed sub-section covering:
- What was being attempted and why
- The exact steps taken (include commands, code snippets, queries)
- What broke and the exact error messages
- How it was debugged (the investigation process)
- What the fix was (with code)
- What was learned

This is the longest and most detailed section. Include:
- Actual error messages and tracebacks verbatim
- Actual commands that were run
- Code snippets for key fixes
- SQL queries if relevant
- Configuration changes

Do NOT summarize — be exhaustively detailed. The reader should be able to reproduce the journey.
Write ONLY this section. Start with "## 3. Key Technical Journey".""",
    },
    "war_stories": {
        "title": "## 4. War Stories & Lessons Learned",
        "max_tokens": 8192,
        "system": """You are writing the "War Stories & Lessons Learned" section of a research narrative.

Write engaging, detailed accounts of:
- The most interesting failures and what they taught
- Unexpected discoveries that changed the direction
- Things that would be done differently in hindsight
- Surprising interactions between different system components

Write in a conference-talk style — the audience should feel the journey.
Include specific technical details that make the stories credible and educational.
Write ONLY this section. Start with "## 4. War Stories & Lessons Learned".""",
    },
    "artifacts": {
        "title": "## 5. Technical Artifacts",
        "max_tokens": 8192,
        "system": """You are writing the "Technical Artifacts" section of a research narrative.

Document ALL technical artifacts produced or discovered during the research:
- Key scripts and tools (with actual code)
- Important commands and their syntax
- Configuration files and settings
- SQL queries and database operations
- Reusable patterns and techniques
- Architecture diagrams (in ASCII/text)
- Deployment procedures

Include artifacts VERBATIM where possible — code blocks, exact commands, full configurations.
This section is a reference — someone should be able to use these artifacts directly.
Write ONLY this section. Start with "## 5. Technical Artifacts".""",
    },
    "future_work": {
        "title": "## 6. Open Questions & Future Work",
        "max_tokens": 4096,
        "system": """You are writing the "Open Questions & Future Work" section of a research narrative.

Cover:
- Unresolved questions that came up during the research
- Known limitations of the current approach
- Natural extensions and next steps
- Technical debt identified but not addressed
- Ideas for improvement mentioned but not implemented

Be specific — reference actual issues and their technical context.
Write ONLY this section. Start with "## 6. Open Questions & Future Work".""",
    },
}
