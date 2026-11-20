---
name: commit-message
description: Write a git commit message for code changes. Use when the user asks for a commit message or wants to commit their work.
---

# Commit message

1. If the user did not include the changes, run `git diff --staged` to see them.
2. Write the message in Conventional Commits format: `<type>: <summary>`, where type is one of
   feat, fix, docs, refactor, test or chore.
3. Keep the summary under 72 characters, in the imperative mood, with no trailing period.
4. Do not run `git commit` yourself. Show the message so the user can commit it.
