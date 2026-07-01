# Online Eval Rules Example

Create and manage Opik online evaluation rules via the SDK and REST API, side by side.

## Usage

```bash
cp .env.example .env
# fill in OPIK_API_KEY and OPIK_WORKSPACE in .env

uv run create-online-eval-rules create-llm-judge --name my-rule
```

Set only `OPIK_API_KEY`/`OPIK_WORKSPACE` missing to run in `DRY_RUN` mode (prints SDK + curl without executing).
