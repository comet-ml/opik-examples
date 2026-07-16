# Agent instructions for opik-examples

This repo is a reference library of examples and utilities for [Opik](https://www.comet.com/site/products/opik/), Comet's LLM evaluation and observability platform. Read this file before generating or editing any code.

## Repo structure

```
opik-examples/
├── integrations/   # Adding Opik to a specific framework or library
├── guides/         # How-to patterns for Opik workflows
├── use-cases/      # End-to-end applications and domain workflows
├── scripts/        # Utility automations and API helpers
└── templates/      # Starter templates (use-case-template, script-template)
```

**Which bucket does new code belong in?**

| If you are… | Put it in |
|---|---|
| Integrating an external framework (LangGraph, OTel, Pydantic AI, OpenAI SDK…) | `integrations/` |
| Showing how to do something with Opik itself, or combining Comet products | `guides/` |
| Building a complete application that uses Opik as an ingredient | `use-cases/` |
| Automating or managing Opik resources programmatically | `scripts/` |

When adding a new example, use the [`scaffold-example`](.claude/skills/scaffold-example/SKILL.md) skill — it stamps one of two templates into the right bucket and renames it for you: `templates/use-case-template/` (full Opik-loop skeleton: `uv` project, `src/<pkg>/`, ruff, Typer CLI) for end-to-end demos, or `templates/script-template/` (single-file argparse utility, `--bucket scripts --template script-template`) for standalone scripts. Folder names must be lowercase with underscores.

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

### Dependencies — uv + pyproject.toml

Every example is a `uv` project: its `pyproject.toml` is the single source of truth for dependencies. **No `requirements.txt`, no Poetry.** Install with `uv sync`, run with `uv run` (`uv run python <file>.py`, or the `[project.scripts]` command if one is defined). Don't commit `uv.lock`. The README's Prerequisites still shows a one-line install (`uv sync`, with an optional `pip install` fallback). Do not assume the repo root virtualenv is active.

## Coding best practices

- **Principles:** DRY, KISS, SOLID, YAGNI. Prefer reusing an existing helper over adding a new one.
- **Type hints** on function signatures. Match the surrounding file's style, naming, and comment density.
- **Git / PR safety:**
  - **Claim the tracking issue before starting.** Work is tracked in [GitHub Issues](https://github.com/comet-ml/opik-examples/issues) — comment on the relevant issue to claim it before writing code. If none exists, ask the user whether to open one (via the *Example proposal* form).
  - **Open a draft PR that links the issue early.** Right after cutting the branch, open a **draft** PR with `Closes #<issue>` in the body so in-flight work is visible; mark it ready for review only when complete.
  - Never `git commit` or `git push` on `main`/`master`. Cut a feature branch (`<user>/<topic>`, e.g. `fschlz/feature/...`), push there, open a PR, and let a human merge.
  - Commits follow **Conventional Commits**: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`.
  - Never `gh pr merge`, `gh pr close`, or `gh pr review --approve` — author/reviewer actions only. Blocked in [`.claude/settings.json`](.claude/settings.json).
  - No AI-attribution footers in commit messages or PR bodies.
  - **Update READMEs before opening a PR.** Refresh the example's own `README.md`, and when you add, rename, or remove an example, update the bucket index (e.g. [`use-cases/README.md`](use-cases/README.md)) and the root [`README.md`](README.md) table.

## Opik SDK reference

The [`use-cases/f1_radio_rag`](use-cases/f1_radio_rag) example is the worked, runnable reference for the full loop (dataset → test suite → eval → optimize → Prompt Library). The `.claude/skills/` workflows below automate each step. All snippets assume the env-var + `DRY_RUN` conventions above.

- **Client & tracing** — `client = opik.Opik()` (env-driven; never hardcode workspace/keys). Decorate the function under test with `@opik.track(project_name=...)` so each call is a trace. See [`rag.py`](use-cases/f1_radio_rag/src/f1_radio_rag/rag.py).
- **Datasets** — `dataset = client.get_or_create_dataset(name)` then `dataset.insert([{...}, ...])`. Opik content-hashes items, so re-inserting identical items is deduped (safe to re-run). Skill: [`add-dataset-items`](.claude/skills/add-dataset-items/SKILL.md).
- **Test suites** — `suite = client.get_or_create_test_suite(name, global_assertions=[...], global_execution_policy={"runs_per_item": N, "pass_threshold": N})` then `suite.insert([{"data": {...}, "assertions": [...]}])`. Assertions are plain-English, grounded in the item's context. Skill: [`add-eval-suite-items`](.claude/skills/add-eval-suite-items/SKILL.md).
- **Running evals** — `from opik.evaluation import evaluate, run_tests` and `from opik.evaluation.metrics import ContextRecall, Hallucination, AnswerRelevance`. The task is `(item: dict) -> dict` returning `{"input", "output", "context"}`. `run_tests(...)` exposes `.pass_rate` / `.experiment_url`; `evaluate(dataset, task, scoring_metrics=[...], experiment_name=...)` runs the metrics. Skill: [`run-evals`](.claude/skills/run-evals/SKILL.md).
- **Optimization** — `from opik_optimizer import ChatPrompt, MetaPromptOptimizer`. `optimizer.optimize_prompt(prompt, dataset, metric, max_trials, n_samples)` returns `.initial_score`, `.score`, `.get_run_link()`, `.prompt.get_messages()`. The metric is a plain callable `(dataset_item: dict, llm_output: str) -> float` with `__name__` set. It tunes the prompt/params, not the retriever. Skill: [`run-optimizations`](.claude/skills/run-optimizations/SKILL.md).
- **Prompt Library** — `client.create_chat_prompt(name, messages, change_description, tags)`. Upsert: re-using `name` appends a new version. See [`prompts.py`](use-cases/f1_radio_rag/src/f1_radio_rag/prompts.py).

## Every example must have a README.md

Required sections:

1. **What this does** — one paragraph describing the problem and the solution
2. **Prerequisites** — `pip install` line and a table of environment variables
3. **Running it** — exact commands, dry-run first
4. **How it works** — brief walkthrough of the key steps

See `templates/use-case-template/README.md` for the exact structure to follow. Keep the README in sync with the code and update it before every PR.

## Full contribution guide

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete standards, the recommended plan → brainstorm → branch → implement → test → READMEs → PR → review workflow, and the PR checklist.
