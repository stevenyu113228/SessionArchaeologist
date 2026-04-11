"""Parse user feedback YAML files for the refinement loop."""

from __future__ import annotations

from pathlib import Path

import yaml


def parse_feedback(path: Path) -> list[dict]:
    """Parse a feedback YAML file into a list of annotation dicts.

    Expected format:
    annotations:
      - section: "key_technical_journey.phase_2"
        type: correction
        content: "Actually the reason I tried this was because..."
      - section: "war_stories.item_1"
        type: needs_detail
        content: "This debug process is too brief, please add more detail"
      - section: "methodology_evolution"
        type: injection
        content: "Before switching to plan B, I heard a talk at DEF CON..."
      - section: "research_overview"
        type: tone_change
        tone: "war_story"
        content: ""
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    annotations = data.get("annotations", [])
    validated = []
    for ann in annotations:
        if not isinstance(ann, dict):
            continue
        validated.append({
            "section": ann.get("section", ""),
            "type": ann.get("type", "correction"),
            "content": ann.get("content", ""),
            "tone": ann.get("tone", ""),
        })
    return validated
