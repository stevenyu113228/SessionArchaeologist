"""Slide outline export — structured for PPTX generation."""

from __future__ import annotations

import re


def narrative_to_slide_outline(markdown_text: str) -> str:
    """Convert a narrative into a slide outline format.

    Maps markdown sections to slides with key points.
    """
    slides = []
    current_slide = None

    for line in markdown_text.split('\n'):
        h1 = re.match(r'^#\s+(.+)', line)
        h2 = re.match(r'^##\s+(.+)', line)
        h3 = re.match(r'^###\s+(.+)', line)

        if h1:
            current_slide = {"title": h1.group(1).strip(), "points": [], "notes": ""}
            slides.append(current_slide)
        elif h2:
            current_slide = {"title": h2.group(1).strip(), "points": [], "notes": ""}
            slides.append(current_slide)
        elif h3 and current_slide:
            current_slide["points"].append(f"**{h3.group(1).strip()}**")
        elif current_slide and line.strip().startswith('- '):
            current_slide["points"].append(line.strip()[2:])
        elif current_slide and line.strip():
            current_slide["notes"] += line.strip() + " "

    # Format as readable outline
    output = "# Slide Outline\n\n"
    for i, slide in enumerate(slides, 1):
        output += f"## Slide {i}: {slide['title']}\n\n"
        if slide["points"]:
            output += "**Key Points:**\n"
            for p in slide["points"][:6]:  # max 6 bullets per slide
                output += f"- {p}\n"
            output += "\n"
        if slide["notes"]:
            notes = slide["notes"][:300]
            output += f"**Speaker Notes:** {notes}\n\n"
        output += "---\n\n"

    output += f"\n*Total slides: {len(slides)}*\n"
    return output
