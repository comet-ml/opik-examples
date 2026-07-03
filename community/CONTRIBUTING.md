# Contributing to the Community folder

This folder showcases work the open-source community has built with Opik. It is
deliberately **lighter-weight than the main repo contract** — the strict
`run.sh` / dry-run / litellm / CI rules in the root
[CONTRIBUTING.md](../CONTRIBUTING.md) do **not** apply here. Community entries
are not executed by CI; a maintainer reviews (and, for hosted entries, runs)
them by hand.

There is one thing we always require: **proof you actually logged with Opik** —
either Comet cloud or the self-hosted open-source platform.

## Two kinds of entry

- **Listed** (default): a folder describing your work with links out to your own
  repo/blog/notebook. No code needs to live here.
- **Hosted**: standout, real-world projects we promote into this repo with their
  code included. You submit as *listed*; a maintainer sets `hosted: true` and
  moves your code in when promoting. We also spotlight promoted work in our
  community forums.

## Add your entry

1. Copy `templates/entry-template/` to `community/<your-handle>_<project>/`
   (lowercase, underscores, e.g. `jane_support_agent`).
2. Fill in `meta.yaml` (all fields) and `README.md` (all four sections).
3. Replace `opik-proof.png` with a real screenshot of your Opik traces or
   dashboard.
4. If you want it considered for hosting, include your code in the folder — it
   must genuinely use Opik (`import opik`, `@opik.track`, ...).
5. Regenerate the index: `cd community/scripts && uv run python build_index.py`
   (commit the updated `community/README.md`).
6. Open a PR. A maintainer reviews it.

## What the automated check enforces

`community/scripts/check_entry.py` runs on your PR (a hard gate). It does **not**
run your code. It checks:

- `meta.yaml` has all required fields, at least one link, and a valid
  `opik_platform`.
- `README.md` has all four sections filled in (no leftover `TODO`).
- `opik-proof.png` exists and is referenced from your README.
- No `.env` file or hardcoded API keys are committed.
- Hosted entries contain code that uses Opik.
- The folder name is `lowercase_with_underscores`.
