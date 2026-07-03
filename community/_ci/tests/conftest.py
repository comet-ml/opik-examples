from __future__ import annotations

import base64
from pathlib import Path

import yaml

# Smallest valid PNG (1x1 transparent), base64-encoded.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

_DEFAULT_META = {
    "title": "Real-time support agent with Opik tracing",
    "description": "A support agent traced end-to-end with an LLM-judge eval loop.",
    "author": "jane-doe",
    "links": {"repo": "https://github.com/jane-doe/support-agent"},
    "opik_platform": "cloud",
    "tags": ["agent", "rag"],
    "hosted": False,
}

_DEFAULT_README = """\
# Real-time support agent with Opik tracing

## What I built
A support agent that answers billing questions over a RAG index.

## Problem it solves
Support reps spent hours triaging repeat billing questions.

## What I learned
Opik's span metadata made it obvious which retrieval step was dropping context.

## How I used Opik
Traced each agent turn with `@opik.track`, logged retrieval context in span
metadata, and ran an LLM-judge eval over 40 real tickets. See the screenshot:

![Opik traces](opik-proof.png)
"""


def write_entry(
    base: Path,
    slug: str = "jane_agent",
    *,
    meta: dict | None = None,
    readme: str | None = None,
    include_png: bool = True,
    code: dict[str, str] | None = None,
) -> Path:
    entry = base / slug
    entry.mkdir(parents=True, exist_ok=True)

    merged = dict(_DEFAULT_META)
    if meta:
        for key, value in meta.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
    (entry / "meta.yaml").write_text(yaml.safe_dump(merged, sort_keys=False))

    (entry / "README.md").write_text(_DEFAULT_README if readme is None else readme)

    if include_png:
        (entry / "opik-proof.png").write_bytes(_PNG_1X1)

    for name, contents in (code or {}).items():
        target = entry / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)

    return entry
