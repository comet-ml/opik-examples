"""One place for calls to the Anthropic API: traced client, image blocks, structured JSON."""

from __future__ import annotations

import json
from functools import lru_cache

from anthropic import Anthropic
from opik.integrations.anthropic import track_anthropic

from roadwork_demo.config import get_settings


@lru_cache(maxsize=1)
def client() -> Anthropic:
    s = get_settings()
    # WHY: base_url is always explicit; a shell ANTHROPIC_BASE_URL may point at a proxy.
    return track_anthropic(
        Anthropic(api_key=s.anthropic_api_key, base_url=s.anthropic_api_url),
        project_name=s.opik_project,
    )


def image_block(b64_jpeg: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_jpeg},
    }


def structured_json(
    model: str, system: str, content: list[dict], schema: dict, max_tokens: int
) -> tuple[dict | None, str]:
    """One user turn answered as JSON matching `schema`.

    Returns (parsed, raw_text). parsed is None when the model refused or the text is not JSON.
    """
    response = client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    raw = "".join(b.text for b in response.content if b.type == "text")
    if response.stop_reason == "refusal":
        return None, raw or "model refused"
    try:
        return json.loads(raw), raw
    except (json.JSONDecodeError, TypeError):
        return None, raw
