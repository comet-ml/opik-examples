# Agent instructions for opik-examples

This repo is a reference library of examples and utilities for [Opik](https://www.comet.com/site/products/opik/), Comet's LLM evaluation and observability platform. Read this file before generating or editing any code.

## Repo structure

```
opik-examples/
├── integrations/   # Adding Opik to a specific framework or library
├── guides/         # How-to patterns for Opik workflows
├── use-cases/      # End-to-end applications and domain workflows
├── scripts/        # Utility automations and API helpers
└── _template/      # Starter template for new examples
```

**Which bucket does new code belong in?**

| If you are… | Put it in |
|---|---|
| Integrating an external framework (LangGraph, OTel, Pydantic AI, OpenAI SDK…) | `integrations/` |
| Showing how to do something with Opik itself, or combining Comet products | `guides/` |
| Building a complete application that uses Opik as an ingredient | `use-cases/` |
| Automating or managing Opik resources programmatically | `scripts/` |

When adding a new example, copy `_template/` into the right bucket and rename the folder. Folder names must be lowercase with underscores.

## Non-negotiable conventions

### Credentials — always from environment variables

```python
import os

OPIK_API_KEY   = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_URL       = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")
```

Never hardcode keys. Never read from `.env` files in example code.

### Dry-run mode — every runnable script must have one

Detect missing credentials and fall back to local output instead of erroring or sending data:

```python
DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)

if DRY_RUN:
    print("[DRY RUN] would have sent: ...")
else:
    # send to Opik
```

The dry-run output must be meaningful enough to verify the example works correctly without credentials.

### Comments — only when the WHY is non-obvious

Do not add comments that explain what the code does. Use a short `# WHY:` comment only when a behaviour would surprise a reader — a hidden API constraint, a non-obvious ordering requirement, a known gotcha.

Do not write docstrings that restate the function name. One short line is the maximum.

### Dependencies

List all dependencies in the example's `README.md` as a single `pip install` line. Do not assume the repo root virtualenv is active. Include a `requirements.txt` if the example has more than a handful of dependencies.

## Every example must have a README.md

Required sections:

1. **What this does** — one paragraph describing the problem and the solution
2. **Prerequisites** — `pip install` line and a table of environment variables
3. **Running it** — exact commands, dry-run first
4. **How it works** — brief walkthrough of the key steps

See `_template/README.md` for the exact structure to follow.

## Full contribution guide

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete standards and PR checklist.
