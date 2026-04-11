"""Stage 5: Refinement prompt templates."""

CORRECTION_SYSTEM = """You are refining a research narrative based on the author's corrections.
The author has reviewed the narrative and provided corrections or additional context \
that the original LLM synthesis got wrong or missed.

Your task:
1. Read the current section of the narrative
2. Read the author's correction/injection
3. Rewrite the section incorporating the author's input naturally
4. Maintain the same tone and style as the rest of the document
5. Do not lose any other information from the original section

Return ONLY the rewritten section text — no commentary."""


NEEDS_DETAIL_SYSTEM = """You are enriching a research narrative section with more detail from raw source data.
The author flagged this section as needing more detail.

You will receive:
1. The current narrative section
2. The author's note about what's missing
3. Relevant raw turns from the original session

Your task:
- Add the requested detail naturally into the narrative
- Use actual error messages, commands, and technical specifics from the raw data
- Maintain the same tone and style
- Preserve all existing content, just enrich it

Return ONLY the rewritten section text — no commentary."""


TONE_CHANGE_SYSTEM = """You are adjusting the tone of a research narrative section.

Available tones:
- technical_deep_dive: Dense technical detail, code examples, exact error messages. Academic style.
- war_story: Conversational, "you won't believe what happened next", emphasis on the journey and surprises. Conference talk style.
- executive_summary: High-level, focused on outcomes and decisions. Brief.

Rewrite the section in the requested tone while preserving all factual content.

Return ONLY the rewritten section text — no commentary."""
