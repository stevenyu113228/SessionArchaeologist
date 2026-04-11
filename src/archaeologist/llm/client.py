"""LLM client wrapper — Anthropic SDK for Claude, OpenAI SDK for embeddings."""

from __future__ import annotations

import json
import logging

from anthropic import Anthropic
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from archaeologist.config import settings

logger = logging.getLogger(__name__)

# Lazy-initialized clients
_anthropic_client: Anthropic | None = None
_openai_client: OpenAI | None = None


def get_anthropic() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(
            base_url=settings.anthropic_base_url_trimmed,
            api_key=settings.anthropic_auth_token,
        )
    return _anthropic_client


def get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.anthropic_auth_token,
        )
    return _openai_client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
def chat_completion(
    messages: list[dict],
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 16384,
    temperature: float = 0.3,
) -> str:
    """Send a chat completion request via Anthropic Messages API.

    Returns the text content of the assistant response.
    """
    client = get_anthropic()
    use_model = model or settings.extraction_model

    kwargs: dict = {
        "model": use_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    logger.info("Calling %s (max_tokens=%d)", use_model, max_tokens)
    response = client.messages.create(**kwargs)

    # Extract text from response
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)

    result = "\n".join(text_parts)
    logger.info(
        "Response: %d chars, usage: in=%d out=%d",
        len(result),
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    return result


def chat_completion_json(
    messages: list[dict],
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 16384,
    temperature: float = 0.2,
) -> dict:
    """Chat completion that parses the response as JSON.

    Adds instruction to respond in JSON and strips markdown fences if present.
    """
    # Append JSON instruction to system prompt
    json_system = (system or "") + "\n\nYou MUST respond with valid JSON only. No markdown fences, no explanation."

    text = chat_completion(
        messages=messages,
        model=model,
        system=json_system,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        # Remove first line (```json or ```)
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Generate embeddings via OpenAI-compatible API."""
    client = get_openai()
    use_model = model or settings.embedding_model

    response = client.embeddings.create(model=use_model, input=texts)
    return [item.embedding for item in response.data]


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate API cost in USD."""
    # Rates per 1M tokens
    rates = {
        "claude-4.6-sonnet": {"input": 3.0, "output": 15.0},
        "claude-4.6-opus": {"input": 15.0, "output": 75.0},
        "claude-4.5-sonnet": {"input": 3.0, "output": 15.0},
        "claude-4.5-opus": {"input": 15.0, "output": 75.0},
    }
    r = rates.get(model, {"input": 5.0, "output": 25.0})
    return (input_tokens / 1_000_000) * r["input"] + (output_tokens / 1_000_000) * r["output"]
