---
name: github-issue-lookup
description: Look up GitHub issues and pull requests with the gh CLI. Use for any request about an issue or pull request, including requests to close, edit, comment on or merge one, which this skill does not allow.
---

# GitHub issue lookup

Use the `gh` CLI. This skill only reads.

| Question | Command |
|---|---|
| Issue details or status | `gh issue view <number> --repo <owner>/<repo>` |
| Issue comments | `gh issue view <number> --repo <owner>/<repo> --comments` |
| Pull request details | `gh pr view <number> --repo <owner>/<repo>` |
| Open issues | `gh issue list --repo <owner>/<repo> --state open` |

Never run a command that changes anything (`gh issue close`, `gh issue edit`, `gh issue comment`,
`gh pr merge`, ...). If the user asks for a change, say that this skill can only read, and give
them the command to run themselves.

If `gh` says you are not logged in, stop: do not retry or try other commands. Tell the user to run
`gh auth login`.

Always include the issue or pull request number in the answer.
