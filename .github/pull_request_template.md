## What & why

<!-- What does this PR change, and why? Link any related issue. -->

## Checklist

<!-- See CONTRIBUTING.md for details. Tick what applies; delete rows that don't. -->

- [ ] Example is in the right bucket (`integrations` / `guides` / `use-cases` / `scripts`)
- [ ] Folder name is `lowercase_with_underscores`
- [ ] `README.md` has all required sections; index tables updated if examples were added/renamed/removed
- [ ] Dry-run works with no credentials — `bash run.sh` exits cleanly (this is what CI's secrets-free job runs)
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] No credentials or `.env` files committed
- [ ] Dependencies declared in `pyproject.toml` (uv project); no `requirements.txt`, no committed `uv.lock`
- [ ] `run.sh` exists and starts with `set -e`
- [ ] `OPIK_PROJECT_NAME` is set — exported in `run.sh` (scripts) or defined in `config.py` (use-cases/guides)
- [ ] Examples that call LLMs use litellm and read `OPIK_EXAMPLES_MODEL`
