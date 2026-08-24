# Prompt Versioning

Version prompts in the Opik Prompt Library, compare versions for hallucination with side-by-side experiments, and run traced inference against prompt versions via LiteLLM.

## What this does

Every call to `client.create_prompt(name=..., prompt=...)` with the same `name` creates a new, immutable **commit** rather than overwriting the previous one — so you always have a history of what a prompt used to say, and can fetch any specific version by its commit hash.

This notebook walks through the full loop:
- **Prompt versioning**: Commit two versions of a prompt using `client.create_prompt` with descriptive `change_description` labels.
- **Version retrieval**: Fetch specific commits by hash or retrieve the newest commit using `client.get_prompt`.
- **Traced inference**: Fetch the latest prompt version dynamically and run inference via `litellm`, traced with `@opik.track`.
- **Side-by-side evaluation**: Build an Opik dataset and score two prompt versions for hallucination using `evaluate_prompt` and the `Hallucination` metric, creating side-by-side experiments in the Opik UI.

## Prerequisites

You need an Opik account to follow along — the value of this guide is watching prompt versions, traces, and experiment comparisons render live in Opik.

| Variable | Required for | Description |
|---|---|---|
| `OPIK_API_KEY` | All sections | Your Opik API key |
| `OPIK_WORKSPACE` | All sections | Your Opik workspace name |
| `OPENAI_API_KEY` (or provider key) | Inference & Evaluation | API key for your LLM provider (e.g. OpenAI key for `openai/gpt-5.6-sol`) |
| `OPIK_EXAMPLES_MODEL` | Inference & Evaluation | Optional. Model used via LiteLLM for generation and judging (defaults to `openai/gpt-5.6-sol`) |

## Running it

Open the notebook in Colab (badge below), or run it locally in a uv-managed environment:

```bash
uv sync
uv run --with jupyter jupyter lab
```

Then open `prompt_versioning.ipynb`.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/comet-ml/opik-examples/blob/main/guides/prompt_versioning/prompt_versioning.ipynb)

## How it works

1. **Creating prompt versions.** `client.create_prompt(name=..., prompt=..., change_description=...)` creates immutable prompt versions ("commits"). Using `change_description` labels each version's purpose, which renders in the Opik UI.
2. **Fetching prompt versions.** `client.get_prompt(name=...)` retrieves the latest committed version when `commit` is omitted. Passing `commit="<hash>"` fetches historical versions by their hash.
3. **Running traced inference with LiteLLM.** The inference function is decorated with `@opik.track(project_name=...)` and uses `litellm.completion()`. Fetching the latest prompt dynamically ensures the application runs the newest prompt without hardcoding string templates.
4. **Side-by-side evaluation.** `evaluate_prompt()` scores prompt versions against an Opik dataset using an LLM-as-judge `Hallucination` metric. Each run creates a distinct experiment in Opik so you can compare metrics side-by-side before promoting a prompt version to production.
