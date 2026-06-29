---
name: scaffold-example
description: Scaffold a brand-new Opik example in this repo from a canonical template under templates/ — either a full use-case demo (templates/use-case-template/) or a standalone utility script (templates/script-template/). Use this whenever the user wants to create, add, or start a new use-case, demo, example, example project, or Opik utility script — phrasings like "create a new use case", "add a demo for X", "scaffold an Opik example", "start a new demo like f1_radio_rag", "set up a new example project", "add a script that does X", or describes a new application or utility they want to build on Opik. Do NOT hand-build the folder structure or copy files manually — this skill stamps out the project and renames it correctly. Require a name and a one-line description of what it does; refuse to invent a demo from nothing.
---

# Scaffold a new Opik example

This repo has two canonical shapes, each a real, runnable template under `templates/`:

- **[`templates/use-case-template/`](../../../templates/use-case-template)** (default) — the
  `f1_radio_rag` shape: a `uv` project with a `src/<pkg>/` package, ruff, a Typer CLI wired
  through the full Opik loop (traced app → dataset + test suite → `evaluate`/`run_tests` →
  optimizer → Prompt Library), `data/` fixtures, 4-section README. For end-to-end demos.
- **[`templates/script-template/`](../../../templates/script-template)** — the `scripts/` shape: a
  single `.py` file with an argparse CLI, env-var credentials + DRY_RUN, ruff, and a 4-section
  README. For standalone utilities (trace cleanup, exports, dashboards).

Getting either right by hand is fiddly and easy to drift on. This skill copies the chosen template
and renames it, so you start from something that already runs in DRY_RUN and passes `ruff`.

## When to refuse

You need two things:

- A **name** (e.g. `support_ticket_summarizer`, `trace_dumper`). It becomes the folder, the
  Python module/package, the project name, and the default CLI command.
- A **one-line description** of what it does.

If either is missing, ask one short question. Don't invent a demo — an empty scaffold with a
guessed purpose wastes the user's time.

## Step 1 — Generate the project

Run the bundled generator. It copies the chosen template, renames its sentinel identity to the new
name, and writes the description. It refuses to overwrite an existing folder.

```bash
# Use-case demo (default template, into use-cases/):
python .claude/skills/scaffold-example/scripts/scaffold.py <name> \
  --description "<one line>"

# Utility script (script template, into scripts/):
python .claude/skills/scaffold-example/scripts/scaffold.py <name> \
  --bucket scripts --template script-template --description "<one line>"

# options: --bucket use-cases (default; or scripts/guides/integrations),
#          --template use-case-template (default) | script-template, --command <cli-name>
```

Pick the template by shape: an end-to-end Opik demo → `use-case-template`; a standalone utility →
`script-template` (with `--bucket scripts`). Naming derived from `<name>`: module + folder are
snake_case, project name is kebab-case, the CLI command defaults to the kebab name (pass
`--command` to override). The script prints the package/project/command it chose and a next-steps
checklist.

## Step 2 — Make it real

> **Script template:** there's no `src/` package — fill the `TODO` in the single `<name>.py`
> (the `run()` body) and the README's 4 sections, then skip to Step 3. The rest of this step is
> use-case-template only.

The scaffold runs as-is but is generic. Fill the parts marked `TODO`, in roughly this order:

- **`data/cases.json`** — replace the sample items with real eval cases for this use case
  (`input`, `expected_output`, `context`, `assertions`). The `add-dataset-items` and
  `add-eval-suite-items` skills cover the item/assertion shapes in depth.
- **`prompts.py`** — the `SYSTEM_PROMPT` and `USER_TEMPLATE` your task needs. The user template
  uses single-brace `{field}` placeholders binding to dataset item keys.
- **`app.py`** — the `@opik.track`-decorated `run()` is the deployed app. Replace its body with
  the real logic (retrieval, tool use, chains). It must return `{"input", "output", "context"}`
  so the metrics can score it.
- **`config.py`** — adjust model strings and the dataset/suite/prompt names if needed.
- **`README.md`** — fill the four sections (What this does / Prerequisites / Running it / How it
  works). This is required for every example (see [AGENTS.md](../../../AGENTS.md)).
- **`pyproject.toml`** — add any extra dependencies the use case needs (e.g. a vector store).

Keep the repo conventions: credentials from env vars only, the `DRY_RUN` fallback intact,
`# WHY:`-only comments.

## Step 3 — Verify

From the new project directory:

```bash
uv sync
uv run <command> eval        # use-case: [DRY RUN] lists the dataset items + assertions
uv run <command> optimize    # use-case: [DRY RUN] line
uv run <command> --dry-run   # script: [DRY RUN] line
uv run ruff check .          # clean
```

With credentials set (`ANTHROPIC_API_KEY`, `OPIK_API_KEY`, `OPIK_WORKSPACE`), the same commands
talk to Claude + Opik and `eval` prints a pass rate + experiment URL. Running the eval and
optimization workflows in depth is covered by the `run-evals` and `run-optimizations` skills.

## What this skill does NOT do

- **No git commit / PR.** Leave the new files in the working tree for the user to review.
- **No domain logic.** It scaffolds; you (with the user) write the actual app, prompts, and data.
