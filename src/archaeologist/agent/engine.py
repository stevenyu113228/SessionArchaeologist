"""ReAct Agent Engine — iterative tool-use loop using Anthropic native API."""

from __future__ import annotations

import json
import logging
from typing import Callable

from archaeologist.llm.client import get_anthropic

logger = logging.getLogger(__name__)


def run_agent(
    task: str,
    tools: list[dict],
    tool_handler: Callable[[str, dict], str],
    model: str,
    system: str = "",
    max_iterations: int = 15,
    on_step: Callable[[dict], None] | None = None,
) -> str:
    """Run a ReAct agent loop.

    The agent receives a task and a set of tools. It can call tools iteratively
    until it produces a final text response (stop_reason == "end_turn").

    Args:
        task: The task description sent as the initial user message.
        tools: Anthropic tool definitions (list of dicts with name, description, input_schema).
        tool_handler: Function(tool_name, tool_input) -> str result.
        model: Model ID to use.
        system: System prompt.
        max_iterations: Max tool-use rounds before forced stop.
        on_step: Optional callback for each step (for progress reporting).

    Returns:
        The agent's final text response.
    """
    client = get_anthropic()
    messages = [{"role": "user", "content": task}]

    for iteration in range(max_iterations):
        logger.info("Agent iteration %d/%d", iteration + 1, max_iterations)

        response = client.messages.create(
            model=model,
            max_tokens=16384,
            system=system,
            tools=tools,
            messages=messages,
        )

        # Collect text and tool_use blocks from response
        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        if on_step:
            on_step({
                "iteration": iteration + 1,
                "tool_calls": [{"name": tc.name, "input": tc.input} for tc in tool_calls],
                "has_text": bool(text_parts),
                "stop_reason": response.stop_reason,
            })

        # If no tool calls — agent is done
        if response.stop_reason == "end_turn" or not tool_calls:
            final_text = "\n".join(text_parts)
            logger.info("Agent done after %d iterations (%d chars)", iteration + 1, len(final_text))
            return final_text

        # Execute tool calls and build tool_result messages
        # First, append the assistant's response (with tool_use blocks)
        messages.append({"role": "assistant", "content": response.content})

        # Then append tool results
        tool_results = []
        for tc in tool_calls:
            logger.info("Tool call: %s(%s)", tc.name, json.dumps(tc.input)[:200])
            try:
                result = tool_handler(tc.name, tc.input)
            except Exception as e:
                result = f"Error: {e}"
                logger.warning("Tool error: %s — %s", tc.name, e)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result[:10000],  # cap result size
            })

        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached
    logger.warning("Agent hit max iterations (%d)", max_iterations)
    return "\n".join(text_parts) if text_parts else "(Agent reached max iterations without final response)"
