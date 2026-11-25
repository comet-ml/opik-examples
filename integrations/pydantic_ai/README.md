# Pydantic AI + Opik

Trace a Pydantic AI agent run to Opik using Logfire's OpenTelemetry instrumentation.

## What this does

This example runs a minimal [Pydantic AI](https://ai.pydantic.dev/) agent and sends the agent, model,
and wrapper spans to Opik. It configures Logfire's Pydantic AI instrumentation, registers Opik's
OpenTelemetry span processor, and wraps the agent call in `@opik.track` so the trace has a clean
application entrypoint.

## Prerequisites

This is a `uv` project - dependencies live in `pyproject.toml`.

```bash
uv sync
```

Or, with `pip`:

```bash
pip install opik pydantic-ai "logfire[httpx]"
```

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | for a live run | Opik API key from [comet.com/opik](https://www.comet.com/opik). Unset -> DRY_RUN. |
| `OPIK_WORKSPACE` | for a live run | Your Opik workspace. Unset -> DRY_RUN. |
| `OPENAI_API_KEY` | for the default live run | Provider key for the default `openai:gpt-4o-mini` model. Unset -> DRY_RUN. |
| `PYDANTIC_AI_MODEL` | no | Pydantic AI model name (default `openai:gpt-4o-mini`). |
| `OPIK_PROJECT_NAME` | no | Project traces are logged to (default `pydantic-ai`). |
| `OPIK_OTLP_ENDPOINT` | no | OTLP endpoint for self-hosted or enterprise Opik. |
| `OTEL_EXPORTER_OTLP_HEADERS` | no | Override OTLP headers when you need custom auth or workspace routing. |

## Running it

```bash
# Dry-run first - no credentials needed.
uv run pydantic-ai-opik --dry-run

# Full run - set credentials, then the same command calls the model and logs to Opik.
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"
export OPENAI_API_KEY="<your-openai-key>"

uv run pydantic-ai-opik

# or run it the way CI does:
bash run.sh
```

## How it works

1. **Configure OTLP** - `main.py` sets the Opik OTLP endpoint, headers, and project name from
   environment variables when you run live.
2. **Instrument Pydantic AI** - `logfire.instrument_pydantic_ai()` creates spans for the agent run
   and model call.
3. **Merge spans into one Opik trace** - `OpikSpanProcessor` links Logfire/OpenTelemetry spans to
   the active `@opik.track` trace so the Opik UI shows one nested trace for the full call.
4. **Stay safe by default** - missing Opik or provider credentials switch the script into DRY_RUN,
   which prints the planned model, project, thread ID, and question without making network calls.
