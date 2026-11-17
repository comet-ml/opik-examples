"""One place for LLM calls: litellm traced by Opik, image parts, structured JSON."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from typing import Any

from roadwork_demo.config import get_settings
from roadwork_demo.images import data_uri


@cache
def completion() -> Callable[..., Any]:
    """litellm.completion wrapped so each call is an LLM span with tokens and cost."""
    import litellm
    from opik.integrations.litellm import track_completion

    return track_completion(project_name=get_settings().project)(litellm.completion)


def image_block(b64_jpeg: str) -> dict:
    return {"type": "image_url", "image_url": {"url": data_uri(b64_jpeg)}}


def structured_json(
    model: str, system: str, content: list[dict], schema: dict, max_tokens: int
) -> tuple[dict | None, str]:
    """One user turn answered as JSON matching `schema`.

    Returns (parsed, raw_text). parsed is None when the model refused or the text is not a JSON object.
    """
    response = completion()(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": schema, "strict": True},
        },
        # WHY: evaluate() aborts the whole experiment on a task error, so ride out rate limits.
        num_retries=3,
    )
    choice = response.choices[0]
    raw = choice.message.content or ""
    if not raw:
        return None, f"model returned no text (finish_reason: {choice.finish_reason})"
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, raw
    return (parsed if isinstance(parsed, dict) else None), raw
