"""Stage 2: Intelligent chunking — split sessions respecting narrative boundaries."""

from __future__ import annotations

import logging
from datetime import timedelta

from archaeologist.config import settings

logger = logging.getLogger(__name__)

# Time gap threshold for a "natural" split point (30 minutes)
LARGE_GAP_SECONDS = 30 * 60


def chunk_session(turns: list[dict], manifest: dict) -> list[dict]:
    """Split turns into overlapping chunks respecting narrative boundaries.

    Args:
        turns: List of turn dicts with turn_index, token_estimate, timestamp, role, etc.
        manifest: Session manifest with hot_zones and compact_boundaries.

    Returns:
        List of chunk metadata dicts.
    """
    if not turns:
        return []

    target = settings.chunk_target_tokens
    overlap = settings.chunk_overlap_tokens
    lookahead = settings.chunk_lookahead_tokens

    hot_zones = manifest.get("hot_zones", [])
    compact_boundaries = set(manifest.get("compact_boundaries", []))

    # Build protected ranges (hot zones + compact boundary regions)
    protected_ranges = _build_protected_ranges(turns, hot_zones, compact_boundaries)

    chunks: list[dict] = []
    chunk_start = 0
    chunk_index = 0

    while chunk_start < len(turns):
        # Accumulate tokens until we hit target
        accumulated = 0
        cursor = chunk_start

        while cursor < len(turns) and accumulated < target:
            accumulated += turns[cursor]["token_estimate"]
            cursor += 1

        # If we've consumed all remaining turns, this is the last chunk
        if cursor >= len(turns):
            chunk_data = _make_chunk(
                turns, chunk_start, len(turns) - 1, chunk_index,
                chunks, overlap, hot_zones, compact_boundaries,
            )
            chunks.append(chunk_data)
            break

        # Find the best split point near cursor within ±lookahead
        split_idx = _find_split_point(
            turns, cursor, lookahead, protected_ranges,
        )

        chunk_data = _make_chunk(
            turns, chunk_start, split_idx, chunk_index,
            chunks, overlap, hot_zones, compact_boundaries,
        )
        chunks.append(chunk_data)

        # Next chunk starts at split_idx + 1, minus overlap
        overlap_start = _compute_overlap_start(turns, split_idx, overlap)
        chunk_start = overlap_start
        chunk_index += 1

    logger.info("Created %d chunks from %d turns", len(chunks), len(turns))
    return chunks


def _find_split_point(
    turns: list[dict],
    cursor: int,
    lookahead: int,
    protected_ranges: list[tuple[int, int]],
) -> int:
    """Find the best split point near cursor.

    Priority:
    1. Large time gap (> 30 min)
    2. User message starting new topic (no tool_result in content)
    3. End of tool sequence (assistant response after tool_result)
    4. Any user message (fallback)
    """
    # Search window: cursor ± lookahead (in token terms, but we approximate by turns)
    search_start = max(0, cursor - _tokens_to_turns(lookahead, turns, cursor, direction=-1))
    search_end = min(len(turns) - 1, cursor + _tokens_to_turns(lookahead, turns, cursor, direction=1))

    candidates: list[tuple[int, int]] = []  # (priority, turn_index)

    for i in range(search_start, search_end + 1):
        # Skip if inside a protected range
        if _in_protected_range(i, protected_ranges):
            continue

        turn = turns[i]
        prev_turn = turns[i - 1] if i > 0 else None

        # Priority 1: Large time gap
        if prev_turn and turn.get("timestamp") and prev_turn.get("timestamp"):
            gap = (turn["timestamp"] - prev_turn["timestamp"]).total_seconds()
            if gap > LARGE_GAP_SECONDS:
                candidates.append((1, i))
                continue

        # Priority 2: User message that starts a new topic
        if turn["role"] == "user":
            content = turn.get("content_text", "")
            # Heuristic: no tool_result reference = likely new topic
            if "tool_result" not in content and "tool_use_id" not in content:
                candidates.append((2, i))
                continue

        # Priority 3: End of tool sequence
        if (
            turn["role"] == "assistant"
            and not turn.get("tool_calls")
            and prev_turn
            and prev_turn["role"] == "user"
        ):
            # Check if prev was a tool_result
            prev_content = prev_turn.get("content_text", "")
            if "tool_result" in str(prev_turn.get("raw_jsonl_line", {}).get("message", {}).get("content", "")):
                candidates.append((3, i))
                continue

        # Priority 4: Any user message
        if turn["role"] == "user":
            candidates.append((4, i))

    if not candidates:
        # Absolute fallback: split at cursor
        return min(cursor, len(turns) - 1)

    # Pick best candidate (lowest priority number, closest to cursor)
    candidates.sort(key=lambda c: (c[0], abs(c[1] - cursor)))
    return candidates[0][1]


def _tokens_to_turns(token_budget: int, turns: list[dict], from_idx: int, direction: int) -> int:
    """Convert a token budget to approximate number of turns."""
    accumulated = 0
    count = 0
    idx = from_idx
    while 0 <= idx < len(turns) and accumulated < token_budget:
        accumulated += turns[idx]["token_estimate"]
        count += 1
        idx += direction
    return max(1, count)


def _in_protected_range(turn_idx: int, protected_ranges: list[tuple[int, int]]) -> bool:
    """Check if a turn index falls within any protected range."""
    for start, end in protected_ranges:
        if start <= turn_idx <= end:
            return True
    return False


def _build_protected_ranges(
    turns: list[dict],
    hot_zones: list[dict],
    compact_boundaries: set[int],
) -> list[tuple[int, int]]:
    """Build list of (start, end) ranges that should not be split."""
    ranges = []

    # Hot zones
    for hz in hot_zones:
        ranges.append((hz["start_turn"], hz["end_turn"]))

    # Compact boundary regions: protect ±5 turns around each boundary
    for cb_idx in compact_boundaries:
        start = max(0, cb_idx - 5)
        end = min(len(turns) - 1, cb_idx + 5)
        ranges.append((start, end))

    # Merge overlapping ranges
    return _merge_ranges(ranges)


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping ranges."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _compute_overlap_start(turns: list[dict], split_idx: int, overlap_tokens: int) -> int:
    """Find the turn index where the overlap region starts (going backward from split)."""
    accumulated = 0
    idx = split_idx
    while idx > 0 and accumulated < overlap_tokens:
        idx -= 1
        accumulated += turns[idx]["token_estimate"]
    return idx


def _make_chunk(
    turns: list[dict],
    start: int,
    end: int,
    chunk_index: int,
    previous_chunks: list[dict],
    overlap_tokens: int,
    hot_zones: list[dict],
    compact_boundaries: set[int],
) -> dict:
    """Create a chunk metadata dict."""
    chunk_turns = turns[start : end + 1]
    token_estimate = sum(t["token_estimate"] for t in chunk_turns)

    # Count hot zones in this chunk
    hz_count = sum(
        1
        for hz in hot_zones
        if hz["start_turn"] >= turns[start]["turn_index"] and hz["end_turn"] <= turns[end]["turn_index"]
    )

    # Check compact boundaries
    has_compact = any(
        turns[i]["turn_index"] in compact_boundaries for i in range(start, end + 1)
    )

    # Overlap info
    overlap_start = None
    if previous_chunks and chunk_index > 0:
        prev_end = previous_chunks[-1]["end_turn"]
        if turns[start]["turn_index"] <= prev_end:
            overlap_start = turns[start]["turn_index"]

    return {
        "chunk_index": chunk_index,
        "start_turn": turns[start]["turn_index"],
        "end_turn": turns[end]["turn_index"],
        "overlap_start_turn": overlap_start,
        "token_estimate": token_estimate,
        "hot_zone_count": hz_count,
        "contains_compact_boundary": has_compact,
    }
