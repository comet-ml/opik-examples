# Contributing to opik-examples

Thank you for contributing. This repo is a reference library for Opik users — the goal is examples that are easy to find, easy to run, and easy to adapt.

## Recommended workflow

This is the loop we follow for non-trivial contributions. The slash-commands in brackets come from Claude Code plugins (see below) and are optional but recommended. **Start every contribution with `/brainstorming`** to agree on scope, and **finish by reviewing your own PR with `/review`** before asking a human.

1. **Plan first.** Switch Claude Code to plan mode on the best available model with reasoning effort maxed before writing any code.
2. **Brainstorm the scope** (`/brainstorming`) — agree on *what* to build before *how*.
3. **Write the plan** (`/writing-plans`) — turn the agreed scope into an implementation plan.
4. **Cut a feature branch** — `git switch -c <user>/<topic>` (never commit on `main`).
5. **Implement and commit frequently** — small [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`).
6. **Test and fix** — run the example in dry-run (and with credentials if you have them) until it works; `uv run ruff check .` is clean.
7. **Update the READMEs** — the example's own README plus any index tables (see the [PR checklist](#pr-checklist)).
8. **Open a PR with a description** — what changed and why. A human merges it.
9. **Review your own PR** (`/review`) before requesting human review.

**Recommended Claude Code plugins:** `superpowers` (provides `/brainstorming`, `/writing-plans`, and `/review`) and `caveman` (terse output mode). Install `superpowers` from inside Claude Code:

```text
/plugin marketplace add anthropics/claude-plugins-official   # first time only
/plugin install superpowers@claude-plugins-official
```

## Repo structure

```
opik-examples/
├── integrations/     # "I use X framework — how do I add Opik?"
├── guides/           # "How do I do X with Opik?"
├── use-cases/        # End-to-end apps and domain workflows
├── scripts/          # Utility automations and API helpers
└── templates/        # Starter templates (use-case-template, script-template)
```

**Which bucket does my example belong in?**

| Question | Bucket |
|---|---|
| I'm integrating an external framework (LangGraph, OTel, Pydantic AI, OpenAI SDK…) with Opik | `integrations/` |
| I'm showing how to do something with Opik itself, or combining Comet products | `guides/` |
| I'm building a complete application that uses Opik as an ingredient | `use-cases/` |
| I'm automating or managing Opik resources programmatically | `scripts/` |

If you're unsure, open an issue and ask.

## Adding an example

`templates/use-case-template/` is a full, runnable Opik use-case skeleton: a `uv` project with a
`src/<pkg>/` package, ruff config, and a Typer CLI wired through the whole Opik loop (traced app →
dataset + test suite → `evaluate`/`run_tests` → optimizer → Prompt Library). It runs in dry-run
out of the box. New examples start from it.

**Easiest path (recommended):** use the `scaffold-example` skill — it copies a template and
renames it for you. It drives two templates:

```bash
# Full use-case demo (default template, into use-cases/):
python .claude/skills/scaffold-example/scripts/scaffold.py my_use_case \
  --description "What it does" --bucket use-cases

# Standalone utility script (script template, into scripts/):
python .claude/skills/scaffold-example/scripts/scaffold.py my_script \
  --description "What it does" --bucket scripts --template script-template
```

**By hand:** copy the matching template and rename its package/module + the
`example_use_case`/`example-use-case` (or `example_script`/`example-script`) identifiers across
the files:

```bash
cp -r templates/use-case-template use-cases/my_use_case
cp -r templates/script-template scripts/my_script
```

Then, either way:

1. `cd` into the new folder, `uv sync`, and smoke-test: `uv run <command> eval` (use-case) or
   `uv run <command> --dry-run` (script).
2. Fill the `TODO` stubs — use-case: `app.py` (real logic), `prompts.py`, `data/cases.json`;
   script: the single `.py` — and the four `README.md` sections.
3. Confirm dry-run still works without credentials (see [Dry-run mode](#dry-run-mode)) and
   `uv run ruff check .` is clean.
4. Open a PR and fill in the checklist below.

## Standards

### Every example must have

- A `README.md` that explains what problem it solves, what the example does, and how to run it
- A working dry-run mode so anyone can run it locally without an Opik account
- Credentials loaded from environment variables only — no hardcoded keys
- A `run.sh` that exports `OPIK_PROJECT_NAME` and can run the example end-to-end

### README structure

Use the template's README as a guide. Required sections:

- **What this does** — one paragraph, the problem and the solution
- **Prerequisites** — `uv sync` (optional `pip install` fallback) and an env-vars table
- **Running it** — exact commands, including dry-run
- **How it works** — brief walkthrough of the key steps

### Dry-run mode

Every runnable example must work without credentials. The secrets-free CI `dry-run` job runs `bash run.sh` with no Opik or LLM keys set and expects a clean exit — it is the only execution signal a fork PR receives, so a working dry-run path is required, not optional. The standard pattern:

```python
DRY_RUN = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))

if DRY_RUN:
    print("[DRY RUN] would have sent: ...")
else:
    # send to Opik
```

The dry-run output should be meaningful enough to verify the example is working. To see real traces, set your own Opik credentials locally — the same way CI's live run does.

### Credentials

Always load from environment variables:

```python
import os

api_key   = os.environ["OPIK_API_KEY"]
workspace = os.environ["OPIK_WORKSPACE"]
```

Never commit `.env` files or hardcoded keys. Add `.env` to the example's `.gitignore` if the example includes a `.env.example`.

### Dependencies

Each example is a `uv` project: declare dependencies in its `pyproject.toml` (the single source of truth) and run with `uv sync` / `uv run`. No `requirements.txt`, no Poetry, and don't commit `uv.lock`. The README may still show an optional `pip install` fallback line. Do not assume the user has the repo's root virtualenv set up.

### run.sh

Every testable example must include a `run.sh` at its root. This file is what the CI matrix runs. Requirements:

- Start with `set -e` (fail fast on any error)
- Call `uv sync` before invoking any Python
- `OPIK_PROJECT_NAME` must be set — see below for where

```bash
#!/usr/bin/env bash
set -e

uv sync
uv run my-example eval   # the command(s) that run the example end-to-end
```

The scaffold tool adds a working `run.sh` automatically when you create a new example.

### Setting OPIK_PROJECT_NAME

Every example must have a unique project name so its traces are identifiable in Opik. Where you set it depends on the example type:

**Scripts** (single `.py` file, no config module) — export it in `run.sh`:

```bash
export OPIK_PROJECT_NAME="my-script"
```

**Use-cases and guides** (examples with a `config.py`) — define it as a Python constant and pass it explicitly. This keeps all configuration in one place and works even when running Python directly:

```python
# config.py
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "my-use-case")
```

```python
# app.py
@opik.track(project_name=config.OPIK_PROJECT_NAME)
def my_function(): ...
```

The compliance check accepts either pattern — it looks for `OPIK_PROJECT_NAME` in `run.sh` or in any `.py` file in the folder.

### Opik workspace

Live CI runs log to the workspace set in the `OPIK_WORKSPACE` GitHub Actions variable (currently `opik-examples`). Locally, set both vars explicitly to avoid accidentally writing to the shared workspace:

```bash
export OPIK_API_KEY=<your personal key>
export OPIK_WORKSPACE=<your own workspace>
```

`DRY_RUN` gates on both being set, so forgetting either keeps you in dry-run mode — safe by default. The `OPIK_API_KEY` Actions secret must be a service account key with write access to `opik-examples`.

### CI model convention

CI uses a cheap model to keep costs low. The `OPIK_EXAMPLES_MODEL` GitHub Actions variable controls which model is used (currently `anthropic/claude-haiku-4-5-20251001`). All examples that make LLM calls must read this variable.

Use [litellm](https://github.com/BerriAI/litellm) as the model call layer — it routes to any provider via a single unified model name:

```python
import litellm
response = litellm.completion(model=config.GEN_MODEL, messages=[...])
```

In `config.py`, read `OPIK_EXAMPLES_MODEL` with a sensible default for local development:

```python
# CI sets OPIK_EXAMPLES_MODEL to a cheap model (e.g. anthropic/claude-haiku-4-5-20251001).
# Locally, leave it unset to use the full model.
GEN_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", "anthropic/claude-sonnet-4-6")
JUDGE_MODEL = GEN_MODEL
OPTIMIZER_MODEL = GEN_MODEL
```

Model names use litellm's provider-prefixed format: `openai/gpt-4o-mini`, `anthropic/claude-haiku-4-5-20251001`, `google/gemini-1.5-flash`, etc. The compliance check will fail if `litellm` is declared as a dependency but `OPIK_EXAMPLES_MODEL` is not referenced.

### Opik logging

Same-repo PRs and scheduled runs have real Opik credentials (`OPIK_API_KEY`, `OPIK_WORKSPACE`, `OPIK_ENVIRONMENT`), and a `live-run` job logs traces to the `opik-examples` workspace — this is how we verify an example is working, not just that it exits 0. Fork PRs don't receive secrets (GitHub withholds them from forks), so they run only the secrets-free `lint` + `dry-run` jobs; a maintainer runs the live job after review.

`OPIK_ENVIRONMENT` is set automatically in CI; you do not need to set it locally. It tags traces so CI runs are distinguishable from local runs in the Opik UI.

Locally, set your own credentials to log to your personal workspace:

```bash
export OPIK_API_KEY=<your personal key>
export OPIK_WORKSPACE=<your workspace>
```

### Code style

- No comments that explain what the code does — well-named variables and functions do that
- A short `# WHY:` comment is appropriate when a behaviour would surprise a reader (e.g. a non-obvious API constraint)
- No emojis

## PR checklist

Before opening a PR, verify:

- [ ] Example is in the right bucket
- [ ] Folder name is lowercase with underscores (e.g. `my_example`, not `MyExample` or `my-example`)
- [ ] `README.md` has all required sections
- [ ] READMEs updated — the example's `README.md`, and for added/renamed/removed examples the bucket index and the root `README.md` table
- [ ] Dry-run works with no credentials set — `bash run.sh` exits cleanly (this is exactly what CI's secrets-free job runs)
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] No credentials or `.env` files committed
- [ ] Dependencies declared in `pyproject.toml` (uv project); no `requirements.txt`
- [ ] `run.sh` exists and starts with `set -e`
- [ ] `OPIK_PROJECT_NAME` is set — exported in `run.sh` (scripts) or defined in `config.py` (use-cases/guides)
- [ ] Examples that call LLMs use litellm and read `OPIK_EXAMPLES_MODEL` in `config.py`

## Questions

Open an issue or start a discussion. We're happy to help you figure out the right bucket or approach before you write the code.
