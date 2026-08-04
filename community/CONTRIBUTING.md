# Contributing to the Community index

This folder is a **curated, links-only index** of projects the open-source
community has built with [Opik](https://www.comet.com/site/products/opik/).
Your code stays in your own repository — the index just points to it. That
means no sync issues when you update your project, and contributing takes a
couple of minutes.

The strict `run.sh` / dry-run / litellm / CI rules in the root
[CONTRIBUTING.md](../CONTRIBUTING.md) do **not** apply here. Community entries
are not executed by CI; a maintainer reviews each submission by hand.

## Add your project

1. Add one block to [`projects.yaml`](projects.yaml):

   ```yaml
   - title: Your project title
     description: One or two sentences on what you built and how it uses Opik.
     author: your-github-handle
     repo: https://github.com/your-handle/your-project
   ```

2. Open a PR. That's it — you don't need to run anything.

All four fields are required. Keep `description` under 250 characters,
`author` a bare GitHub handle (no `@`, no URL), and `repo` an http(s) link.
Don't edit `README.md` — it is generated from `projects.yaml` automatically
after your PR merges.

## Review bar

A maintainer checks that the linked project genuinely uses Opik (e.g.
`import opik`, `@opik.track`, or Opik dashboards in the docs) and that the
description is accurate. Entries are **community-contributed and not
maintainer-verified** — we curate the list, we don't maintain the projects.

## What the automated check enforces

`community/_ci/check_projects.py` runs on your PR (a hard gate). It only
validates `projects.yaml`:

- Every entry has `title`, `description`, `author`, and `repo` (and no other
  fields).
- `repo` is an http(s) URL and `author` is a valid GitHub handle.
- `description` is at most 250 characters.
- No duplicate titles or repos.

## Promotion

Standout projects that meet the standards of the verified buckets
(`integrations/`, `guides/`, `use-cases/`, `scripts/`) may be invited into the
main repo — the root [CONTRIBUTING.md](../CONTRIBUTING.md) contract applies
there.
