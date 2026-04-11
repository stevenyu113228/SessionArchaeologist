"""Export templates — Opus rewrite prompts for different output formats."""

TEMPLATES = {
    "whitepaper": {
        "name": "Whitepaper",
        "description": "Formal academic/industry whitepaper with full technical detail",
        "system_prompt": """Rewrite the following research narrative as a formal whitepaper.

Structure:
- Abstract (150 words max)
- 1. Introduction
- 2. Background & Related Work
- 3. Methodology
- 4. Results & Findings
- 5. Discussion
- 6. Conclusion
- References (if any tools/projects were mentioned)

Style: Formal, third person, precise technical language. Include all code snippets
and error messages. Suitable for publication or internal research documentation.""",
    },
    "conference_talk": {
        "name": "Conference Talk Notes",
        "description": "Speaker notes for a technical conference presentation (DEF CON / Black Hat style)",
        "system_prompt": """Rewrite the following research narrative as conference talk speaker notes.

Structure:
- Title Slide: catchy title + subtitle
- Slide 1-2: The Problem / Why This Matters
- Slide 3-5: The Journey (chronological, with war stories)
- Slide 6-8: Key Technical Details (what the audience needs to reproduce)
- Slide 9: Demos & Live Examples (note what to show)
- Slide 10: Lessons Learned
- Slide 11: Q&A Prep (anticipated questions + answers)

For each slide, provide:
- SLIDE TITLE:
- KEY POINTS: (bullet points)
- SPEAKER NOTES: (what to say, in casual first-person)
- VISUAL: (what to show on screen — screenshot, code, diagram)

Style: Conversational, first person, emphasis on the journey and surprises.
Include actual commands and error messages for credibility.""",
    },
    "blog_post": {
        "name": "Blog Post",
        "description": "Engaging technical blog post for a developer audience",
        "system_prompt": """Rewrite the following research narrative as a technical blog post.

Structure:
- Hook (compelling opening paragraph)
- TL;DR (3-5 bullet points)
- Main narrative (chronological, with headers for each phase)
- Code blocks and screenshots descriptions where relevant
- Key takeaways section
- Call to action / next steps

Style: Informal but technically precise, second person ("you"), engaging.
Use short paragraphs. Include the debugging war stories — they make it relatable.
Suitable for Medium, dev.to, or a personal engineering blog.""",
    },
    "internal_report": {
        "name": "Internal Report",
        "description": "Concise internal report for stakeholders and team leads",
        "system_prompt": """Rewrite the following research narrative as an internal technical report.

Structure:
- Executive Summary (5 sentences max)
- Objectives
- Approach & Timeline
- Key Findings
- Risks & Open Issues
- Recommendations
- Appendix: Technical Details (for those who want to dig deeper)

Style: Concise, professional, action-oriented. Focus on outcomes and decisions.
Minimize debugging narrative — stakeholders want results, not war stories.
Include timeline and resource estimates where relevant.""",
    },
}


def get_template_prompt(template_key: str) -> str:
    """Get the system prompt for a template."""
    t = TEMPLATES.get(template_key)
    if not t:
        raise ValueError(f"Unknown template: {template_key}. Available: {list(TEMPLATES.keys())}")
    return t["system_prompt"]


def list_templates() -> list[dict]:
    """List available templates."""
    return [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in TEMPLATES.items()
    ]
