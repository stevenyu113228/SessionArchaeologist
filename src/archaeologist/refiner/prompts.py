"""Stage 5: Refinement prompt templates."""

CORRECTION_SYSTEM = """You are refining a research narrative based on the author's corrections.
The author has reviewed the narrative and provided corrections or additional context.

Your task:
1. Read the current section of the narrative
2. Read the author's correction/injection
3. Rewrite the section incorporating the author's input naturally
4. Maintain the same tone and style
5. Do not lose any other information from the original section

Return ONLY the rewritten section text."""


NEEDS_DETAIL_SYSTEM = """You are enriching a research narrative section with more detail.
The author flagged this section as needing more detail.

You have access to tools to search the original session data. Use them to find:
- Actual error messages and tracebacks
- Exact commands that were run
- Code snippets
- Timeline details

Add the requested detail naturally into the narrative using evidence from the source data.
Maintain the same tone and style. Return ONLY the rewritten section text."""


TONE_CHANGE_SYSTEM = """You are adjusting the tone of a research narrative section.

Available tones:
- technical_deep_dive: Dense technical detail, code examples, exact error messages.
- war_story: Conversational, emphasis on the journey and surprises. Conference talk style.
- executive_summary: High-level, focused on outcomes and decisions. Brief.

Rewrite the section in the requested tone while preserving all factual content.
Return ONLY the rewritten section text."""


ADD_SUBSECTION_SYSTEM = """You are adding a new subsection to a research narrative.
The author wants a new subsection under a specific section, on a specific topic.

You have access to tools to search the original session data. You MUST use search_session
to find relevant source material before writing. Base your content entirely on evidence
from the original session — do not fabricate details.

Steps:
1. Use search_session to find relevant turns about the requested topic
2. Read specific turns if needed for more context
3. Write a well-structured subsection with actual technical details from the source

The subsection should:
- Start with a ### heading
- Include actual commands, error messages, code from the source data
- Be detailed and specific, not vague summaries
- Fit naturally under the parent section

Return ONLY the new subsection markdown."""


EXPAND_SYSTEM = """You are expanding a research narrative section with more detail.

You have access to tools to search the original session data. Use them to find
additional evidence to enrich the section:
- Search for specific technical details mentioned briefly
- Find actual error messages, commands, code snippets
- Look for debugging steps, timeline details, context

Rules:
- ONLY add content that is supported by evidence from session data
- DO NOT invent or hallucinate details
- Include actual commands, error outputs, and code verbatim
- Expand the section to roughly 2-3x its current length
- Maintain the same tone and style

Return ONLY the expanded section text."""


SHRINK_SYSTEM = """You are condensing a research narrative section.

Compress the section to roughly 1/3 of its current length while preserving:
- All key technical decisions and their outcomes
- Critical error messages and their resolutions
- Important code snippets and commands
- The chronological flow

Remove:
- Redundant explanations
- Verbose descriptions
- Repeated information
- Non-essential context

Return ONLY the condensed section text."""
