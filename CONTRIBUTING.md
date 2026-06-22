# Contributing to opik-examples

Thank you for contributing. This repo is a reference library for Opik users — the goal is examples that are easy to find, easy to run, and easy to adapt.

## Recommended workflow

This is the loop we follow for non-trivial contributions. The slash-commands in brackets come from Claude Code plugins (see below) and are optional but recommended.

1. **Plan first.** Switch Claude Code to plan mode on the best available model with reasoning effort maxed before writing any code.
2. **Brainstorm the scope** (`/brainstorming`) — agree on *what* to build before *how*.
3. **Write the plan** (`/writing-plans`) — turn the agreed scope into an implementation plan.
4. **Cut a feature branch** — `git switch -c <user>/<topic>` (never commit on `main`).
5. **Implement and commit frequently** — small [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`).
6. **Test and fix** — run the example in dry-run (and with credentials if you have them) until it works; `uv run ruff check .` is clean.
7. **Update the READMEs** — the example's own README plus any index tables (see the [PR checklist](#pr-checklist)).
8. **Open a PR with a description** — what changed and why. A human merges it.
9. **Review the diff** (`/review`) before requesting human review.

**Recommended Claude Code plugins:** `superpowers` (provides `/brainstorming`, `/writing-plans`, and `/review`) and `caveman` (terse output mode).

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

### README structure

Use the template's README as a guide. Required sections:

- **What this does** — one paragraph, the problem and the solution
- **Prerequisites** — pip install line and env vars table
- **Running it** — exact commands, including dry-run
- **How it works** — brief walkthrough of the key steps

### Dry-run mode

Every runnable script should detect missing credentials and fall back to a local mode that prints output to the console instead of sending it to Opik. The standard pattern:

```python
DRY_RUN = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))

if DRY_RUN:
    print("[DRY RUN] would have sent: ...")
else:
    # send to Opik
```

The dry-run output should be meaningful enough to verify the example is working correctly.

### Credentials

Always load from environment variables:

```python
import os

api_key   = os.environ["OPIK_API_KEY"]
workspace = os.environ["OPIK_WORKSPACE"]
```

Never commit `.env` files or hardcoded keys. Add `.env` to the example's `.gitignore` if the example includes a `.env.example`.

### Dependencies

Each example should be runnable with a standard `pip install` one-liner listed in the README. If the example has many dependencies, include a `requirements.txt`. Do not assume the user has the repo's root virtualenv set up.

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
- [ ] Dry-run mode works (no env vars set) prints useful output without errors — e.g. `uv run <command> eval`
- [ ] No credentials or `.env` files committed
- [ ] Dependencies are listed in the README

## Questions

Open an issue or start a discussion. We're happy to help you figure out the right bucket or approach before you write the code.
