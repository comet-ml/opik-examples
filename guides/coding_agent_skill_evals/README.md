# Test coding-agent skills with Opik test suites

Give every coding-agent skill a few tests next to its `SKILL.md`, and get a pass/fail result you can
gate a pull request on.

## What this does

Coding agents such as Claude Code, GitHub Copilot and OpenCode load skills: a `SKILL.md` with a
description that tells the agent when to use it, and instructions for what to do. A skill can break in
two ways: the agent doesn't load it when it should, or it loads it and does the wrong thing. This guide
gives each skill an `evals.yaml` of tests written as plain sentences. One shared script turns each file
into an Opik test suite, runs it against an agent, and exits 1 if any test fails. Adding tests for a new
skill means writing one YAML file; the script does not change.

```
skills/
  commit-message/
    SKILL.md
    evals.yaml        ← the only thing a skill author adds
  github-issue-lookup/
    SKILL.md
    evals.yaml
run_skill_evals.py    ← written once, shared by every skill
```

## Prerequisites

```bash
uv sync               # or: pip install opik litellm pyyaml
```

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | for a real run | Your Opik API key. Unset → the script runs in DRY_RUN |
| `OPIK_WORKSPACE` | for a real run | Your Opik workspace name |
| `ANTHROPIC_API_KEY` | for a real run | Key for the agent and judge models (or your provider's key if you change them) |
| `OPIK_EXAMPLES_MODEL` | No | Agent model in litellm format (default `anthropic/claude-haiku-4-5-20251001`) |
| `OPIK_PROJECT_NAME` | No | Opik project for suites, experiments and traces (default `coding-agent-skill-evals`) |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted Opik (default: Opik Cloud) |

## Running it

```bash
# Dry run first: checks every evals.yaml and prints the tests, no keys needed.
uv run skill-evals --dry-run

# Real run.
export OPIK_API_KEY="<your-key>" OPIK_WORKSPACE="<your-workspace>" ANTHROPIC_API_KEY="<your-key>"
uv run skill-evals skills/github-issue-lookup    # one skill: a new or changed skill in a pull request
uv run skill-evals                               # every skill: nightly, to catch model changes

# The same tests against another agent model.
OPIK_EXAMPLES_MODEL=openai/gpt-4o-mini uv run skill-evals
```

Each skill prints one line with its result and a link to the experiment in Opik:

```
github-issue-lookup: 5/5 tests passed  https://www.comet.com/opik/<workspace>/experiments/...
```

To see a test fail, change step 2 of `skills/commit-message/SKILL.md` to "Start the message with a
gitmoji for the type of change" and run `uv run skill-evals skills/commit-message`. The heuristic
that expects `fix:` and the assertion that expects `docs:` fail, and the script exits 1.

## How it works

### Writing tests

A test is a request plus sentences that must be true about what the agent did. An LLM judge checks
them:

```yaml
assertions:            # optional, checked on every test of this skill
  - The agent did not run any command that changes GitHub.

tests:
  - input: What is the status of issue 1234 in comet-ml/opik?
    assertions:
      - The agent loaded the github-issue-lookup skill.
      - The agent ran gh issue view 1234 with --repo comet-ml/opik.

  - input: Close issue 1234 in comet-ml/opik, it is fixed now.
    assertions:
      - The agent told the user it can only read issues and gave them the command to close it.

  - input: Write a Python function that reverses a string.
    assertions:
      - The agent did not load any skill.
```

Cover three things for every skill:

1. **It loads when it should**, and not for unrelated requests.
2. **It does the right thing**: the right command, endpoint or format.
3. **It respects its rules**, for example read-only.

To test how the agent reacts to a command's result, fake it with `tool_outputs`. Any command containing
the key gets that text back; other commands get "not executed, no output":

```yaml
  - input: Which issues are open in comet-ml/opik?
    tool_outputs:
      "gh ": |
        To get started with GitHub CLI, please run:  gh auth login
    assertions:
      - The agent ran exactly one shell command, gh issue list, and did not retry it.
      - The agent said it could not list the issues because the GitHub CLI is not logged in.
```

For a fact a machine can check exactly, a test can add `heuristics`: Opik's built-in `Equals`,
`Contains` and `RegexMatch` metrics on one of the agent's output fields (`skills_loaded`,
`commands_run` or `answer`). They are free and deterministic, but optional:

```yaml
    heuristics:
      answer: { contains: "fix:" }
```

Make sure every check can fail. Without the faked login error, the agent above still mentions
`gh auth login` as a general tip, so `answer: { contains: gh auth login }` would pass either way. The
assertion about the reason fails without it.

### What the script does

For each skill:

1. Saves `SKILL.md` in the Opik **Prompt Library** as `skill-<name>`. A new version is created only
   when the file changes.
2. Syncs `evals.yaml` into the **test suite** `skill-<name>`. Opik versions the suite on every change.
   There is one suite per skill, so a pull request can run only the skill it changes, and each skill
   gets its own pass-rate history.
3. Runs the suite with `opik.run_tests`. Each test runs 3 times and all 3 runs must pass. The judge
   checks every assertion of a run in one call.
4. If a test has `heuristics`, scores them on the same runs with `opik.evaluate_experiment`, without
   running the agent again. Test suites run judge assertions only, so this is a separate step.
5. Exits 1 if any assertion or heuristic failed.

Each run is an experiment linked to the skill version it tested, with a trace per run showing every
model call and tool call. The judge model (`JUDGE_MODEL`) is one the Opik SDK lets open that trace, so
assertions can also cover command results and the loaded skill text, not only the final answer. To run
this gate on every pull request, see [eval_in_ci](../eval_in_ci/).

### The agent

`run_agent` is a minimal simulated coding agent, called through litellm:

- It sees every skill's name and description, as a real agent does, so tests also catch the wrong
  skill being loaded.
- It can load a skill and run commands. Commands are recorded, not executed, and return the test's
  `tool_outputs` when one matches.

It returns the skills it loaded, the commands it ran and its answer. To test a real agent instead
(OpenCode, Copilot CLI), replace `run_agent` in `make_task` with a function that runs it headless and
returns the same three fields. The tests do not change.

### Why skill descriptions need tests

A skill's rules only apply once the agent loads it. An early version of `github-issue-lookup` described
itself only as "Look up GitHub issues". For "Close issue 1234" the agent sometimes did not load it, so
the read-only rule never applied and it ran `gh issue close`. With 3 runs per test and all 3 required to
pass, the suite caught it. The fix was in the description: it now covers requests to change an issue
too.
