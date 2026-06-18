# Contributing to opik-examples

Thank you for contributing. This repo is a reference library for Opik users — the goal is examples that are easy to find, easy to run, and easy to adapt.

## Repo structure

```
opik-examples/
├── integrations/     # "I use X framework — how do I add Opik?"
├── guides/           # "How do I do X with Opik?"
├── use-cases/        # End-to-end apps and domain workflows
└── scripts/          # Utility automations and API helpers
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

1. Copy `_template/` into the appropriate bucket and rename the folder:
   ```bash
   cp -r _template integrations/my_framework
   ```
2. Fill in `README.md` and rename/edit the stub script(s).
3. Make sure the example runs in dry-run mode without credentials (see [Dry-run mode](#dry-run-mode)).
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
- [ ] Dry-run mode works: `python my_script.py` (no env vars set) prints useful output without errors
- [ ] No credentials or `.env` files committed
- [ ] Dependencies are listed in the README

## Questions

Open an issue or start a discussion. We're happy to help you figure out the right bucket or approach before you write the code.
