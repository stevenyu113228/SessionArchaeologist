"""Stage 1: Parse Claude Code JSONL session files into structured Turn records."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import orjson

logger = logging.getLogger(__name__)

# Patterns that indicate errors in tool output
ERROR_PATTERNS = re.compile(
    r"(Traceback \(most recent call last\)"
    r"|Error:|error:|FAILED|panic:|fatal:|Exception:|"
    r"Permission denied|No such file|command not found"
    r"|ModuleNotFoundError|ImportError|SyntaxError"
    r"|ConnectionRefusedError|TimeoutError)",
    re.IGNORECASE,
)

# Message types we extract as conversation turns
TURN_TYPES = {"user", "assistant", "system"}


def parse_jsonl_file(path: Path) -> tuple[list[dict], dict]:
    """Parse a JSONL file from disk."""
    with open(path, "rb") as f:
        return parse_jsonl_bytes(f.read(), source_path=str(path))


def parse_jsonl_bytes(data: bytes, source_path: str = "upload") -> tuple[list[dict], dict]:
    """Parse JSONL bytes into a list of turn dicts + session manifest.

    Returns:
        (turns, manifest) where turns is a list of extracted turn dicts
        and manifest contains session-level statistics.
    """
    turns: list[dict] = []
    raw_lines: list[dict] = []
    parse_errors = 0
    session_id_found: str | None = None
    session_slug: str | None = None
    version: str | None = None

    for line_num, line in enumerate(data.split(b"\n"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = orjson.loads(line)
        except orjson.JSONDecodeError:
            logger.warning("Unparseable line %d in %s", line_num, source_path)
            parse_errors += 1
            continue
        raw_lines.append(record)

        if not session_id_found and record.get("sessionId"):
            session_id_found = record["sessionId"]
        if not session_slug and record.get("slug"):
            session_slug = record["slug"]
        if not version and record.get("version"):
            version = record["version"]

    # Filter to conversation turns only
    turn_index = 0
    for record in raw_lines:
        rec_type = record.get("type", "")
        if rec_type not in TURN_TYPES:
            continue

        turn = _extract_turn(record, turn_index)
        if turn:
            turns.append(turn)
            turn_index += 1

    manifest = _build_manifest(
        turns=turns,
        session_id=session_id_found,
        session_slug=session_slug,
        version=version,
        source_path=source_path,
        parse_errors=parse_errors,
        total_raw_lines=len(raw_lines),
    )

    return turns, manifest


def _extract_turn(record: dict, turn_index: int) -> dict | None:
    """Extract a structured turn dict from a raw JSONL record."""
    rec_type = record.get("type", "")
    message = record.get("message", {})
    role = message.get("role", rec_type)

    # Flatten content
    content_text, tool_calls, has_thinking, is_tool_result = _flatten_content(message)

    # For system messages without a message field
    if rec_type == "system" and not message:
        subtype = record.get("subtype", "")
        content_text = f"[system:{subtype}]"
        if record.get("hookInfos"):
            content_text += f" hooks: {record['hookInfos']}"

    # Skip empty turns (e.g., attachment-only)
    if not content_text and not tool_calls:
        return None

    # Error detection
    is_error = _detect_error(record, content_text, is_tool_result)

    # Compact boundary detection
    is_compact = _detect_compact_boundary(record, content_text)

    # Token estimate: use actual usage if available, otherwise chars/4
    token_estimate = _estimate_tokens(record, content_text)

    # Timestamp
    timestamp = _parse_timestamp(record.get("timestamp"))

    # Content hash
    content_hash = hashlib.sha256(content_text.encode()).hexdigest()[:16] if content_text else None

    return {
        "turn_index": turn_index,
        "role": role,
        "content_text": content_text,
        "tool_calls": tool_calls if tool_calls else None,
        "is_compact_boundary": is_compact,
        "is_error": is_error,
        "token_estimate": token_estimate,
        "content_hash": content_hash,
        "timestamp": timestamp,
        "raw_jsonl_line": record,
        # Extra fields from JSONL
        "message_uuid": record.get("uuid"),
        "parent_uuid": record.get("parentUuid"),
        "is_sidechain": record.get("isSidechain", False),
        "model_used": message.get("model"),
        "token_usage": message.get("usage"),
        "has_thinking": has_thinking,
    }


def _flatten_content(message: dict) -> tuple[str, list[dict], bool, bool]:
    """Flatten message content blocks into text + tool_calls list.

    Returns (content_text, tool_calls, has_thinking, is_tool_result).
    """
    content = message.get("content", "")
    if isinstance(content, str):
        return content, [], False, False

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    has_thinking = False
    is_tool_result = False

    for block in content:
        block_type = block.get("type", "")

        if block_type == "text":
            text_parts.append(block.get("text", ""))

        elif block_type == "thinking":
            has_thinking = True
            # Include thinking content as it's valuable for research narrative
            thinking_text = block.get("thinking", "")
            if thinking_text:
                text_parts.append(f"[thinking] {thinking_text}")

        elif block_type == "tool_use":
            tool_calls.append({
                "tool_name": block.get("name", ""),
                "tool_use_id": block.get("id", ""),
                "input_summary": _summarize_tool_input(block.get("name", ""), block.get("input", {})),
            })

        elif block_type == "tool_result":
            is_tool_result = True
            result_content = block.get("content", "")
            if isinstance(result_content, str):
                text_parts.append(result_content)
            elif isinstance(result_content, list):
                for sub in result_content:
                    if isinstance(sub, dict) and sub.get("type") == "text":
                        text_parts.append(sub.get("text", ""))

    return "\n".join(text_parts), tool_calls, has_thinking, is_tool_result


def _summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Create a concise summary of tool input."""
    if tool_name == "Bash":
        return tool_input.get("command", "")[:200]
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"read {path}"
    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        return f"write {path}"
    if tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"edit {path}"
    if tool_name == "Grep":
        return f"grep '{tool_input.get('pattern', '')}'"
    if tool_name == "Glob":
        return f"glob '{tool_input.get('pattern', '')}'"
    if tool_name in ("WebSearch", "WebFetch"):
        return tool_input.get("query", tool_input.get("url", ""))[:200]
    if tool_name == "Agent":
        return tool_input.get("description", "")[:200]
    # Generic: first 200 chars of JSON
    return str(tool_input)[:200]


def _detect_error(record: dict, content_text: str, is_tool_result: bool) -> bool:
    """Detect if this turn contains an error."""
    # Explicit error flag in tool results
    message = record.get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        for block in content:
            if block.get("type") == "tool_result" and block.get("is_error"):
                return True

    # toolUseResult with stderr
    tool_result = record.get("toolUseResult", {})
    if tool_result.get("stderr"):
        return True

    # Pattern matching on content for tool results
    if is_tool_result and content_text and ERROR_PATTERNS.search(content_text):
        return True

    return False


def _detect_compact_boundary(record: dict, content_text: str) -> bool:
    """Detect if this turn is a compaction/summary boundary."""
    rec_type = record.get("type", "")

    # Check for summary type
    if rec_type == "summary":
        return True

    # Check for system messages about compaction
    subtype = record.get("subtype", "")
    if "compact" in subtype.lower() or "summary" in subtype.lower():
        return True

    # Check content for compaction markers
    if content_text and any(
        marker in content_text.lower()
        for marker in [
            "conversation has been compressed",
            "previous conversation summary",
            "context was compressed",
            "[compacted]",
        ]
    ):
        return True

    return False


def _estimate_tokens(record: dict, content_text: str) -> int:
    """Estimate token count, preferring actual usage data."""
    message = record.get("message", {})
    usage = message.get("usage", {})

    if usage:
        # For assistant messages, use output_tokens
        output = usage.get("output_tokens", 0)
        if output:
            return output
        # For input, sum available token counts
        total = usage.get("input_tokens", 0)
        total += usage.get("cache_creation_input_tokens", 0)
        total += usage.get("cache_read_input_tokens", 0)
        if total:
            return total

    # Fallback: chars / 4
    return max(1, len(content_text) // 4) if content_text else 0


def _parse_timestamp(ts) -> datetime | None:
    """Parse timestamp from JSONL — handles ISO 8601 strings and epoch ms."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        # Epoch milliseconds
        return datetime.utcfromtimestamp(ts / 1000)
    if isinstance(ts, str):
        # ISO 8601
        ts = ts.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(ts).replace(tzinfo=None)
        except ValueError:
            logger.warning("Unparseable timestamp: %s", ts)
            return None
    return None


def _build_manifest(
    turns: list[dict],
    session_id: str | None,
    session_slug: str | None,
    version: str | None,
    source_path: str,
    parse_errors: int,
    total_raw_lines: int,
) -> dict:
    """Build a session manifest with statistics."""
    total_turns = len(turns)
    total_tokens = sum(t["token_estimate"] for t in turns)

    # Compact boundaries
    compact_boundaries = [t["turn_index"] for t in turns if t["is_compact_boundary"]]

    # Error density map (sliding window of 20 turns)
    error_density = _compute_error_density(turns, window=20)

    # Tool usage timeline
    tool_timeline = _compute_tool_timeline(turns)

    # Hot zones: regions with high turn density in short time spans
    hot_zones = _detect_hot_zones(turns)

    # Time range
    timestamps = [t["timestamp"] for t in turns if t["timestamp"]]
    time_range = None
    if timestamps:
        time_range = {
            "start": timestamps[0].isoformat(),
            "end": timestamps[-1].isoformat(),
            "duration_hours": (timestamps[-1] - timestamps[0]).total_seconds() / 3600,
        }

    return {
        "session_id": session_id,
        "session_slug": session_slug,
        "claude_code_version": version,
        "source_path": source_path,
        "total_turns": total_turns,
        "total_tokens_est": total_tokens,
        "total_raw_lines": total_raw_lines,
        "parse_errors": parse_errors,
        "compact_boundaries": compact_boundaries,
        "error_density": error_density,
        "tool_timeline": tool_timeline,
        "hot_zones": hot_zones,
        "time_range": time_range,
        "role_distribution": _count_roles(turns),
        "error_count": sum(1 for t in turns if t["is_error"]),
        "sidechain_count": sum(1 for t in turns if t["is_sidechain"]),
        "thinking_count": sum(1 for t in turns if t["has_thinking"]),
    }


def _compute_error_density(turns: list[dict], window: int = 20) -> list[dict]:
    """Compute error density over sliding windows."""
    if not turns:
        return []
    density = []
    for i in range(0, len(turns), window // 2):
        window_turns = turns[i : i + window]
        errors = sum(1 for t in window_turns if t["is_error"])
        if errors > 0:
            density.append({
                "start_turn": window_turns[0]["turn_index"],
                "end_turn": window_turns[-1]["turn_index"],
                "error_count": errors,
                "density": errors / len(window_turns),
            })
    return density


def _compute_tool_timeline(turns: list[dict]) -> list[dict]:
    """Compute tool usage frequency timeline."""
    tool_counts: dict[str, int] = {}
    for turn in turns:
        if turn["tool_calls"]:
            for tc in turn["tool_calls"]:
                name = tc["tool_name"]
                tool_counts[name] = tool_counts.get(name, 0) + 1
    return [{"tool": k, "count": v} for k, v in sorted(tool_counts.items(), key=lambda x: -x[1])]


def _detect_hot_zones(turns: list[dict], min_turns: int = 10, max_gap_seconds: float = 120) -> list[dict]:
    """Detect hot zones — regions with rapid turn exchanges.

    A hot zone is a sequence of >= min_turns turns where consecutive
    timestamps are all within max_gap_seconds of each other.
    """
    if not turns:
        return []

    zones = []
    zone_start = None
    zone_turns = 0
    prev_ts = None

    for turn in turns:
        ts = turn["timestamp"]
        if ts is None:
            continue

        if prev_ts is not None and (ts - prev_ts).total_seconds() <= max_gap_seconds:
            zone_turns += 1
        else:
            # Gap too large — close current zone if it qualifies
            if zone_start is not None and zone_turns >= min_turns:
                zones.append({
                    "start_turn": zone_start,
                    "end_turn": turn["turn_index"] - 1,
                    "turn_count": zone_turns,
                })
            zone_start = turn["turn_index"]
            zone_turns = 1

        prev_ts = ts

    # Close final zone
    if zone_start is not None and zone_turns >= min_turns:
        zones.append({
            "start_turn": zone_start,
            "end_turn": turns[-1]["turn_index"],
            "turn_count": zone_turns,
        })

    return zones


def _count_roles(turns: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in turns:
        role = t["role"]
        counts[role] = counts.get(role, 0) + 1
    return counts
