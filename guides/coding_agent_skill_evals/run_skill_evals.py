#!/usr/bin/env python3
"""Evaluate coding-agent skills with Opik test suites.

Each folder under skills/ holds a SKILL.md and an evals.yaml. For each skill this script saves SKILL.md in
the Opik Prompt Library, syncs evals.yaml into a test suite, runs the suite against a small simulated coding
agent, and exits 1 if any test fails, so it can block a pull request.

  uv run skill-evals --dry-run                 # check every evals.yaml; no keys needed
  uv run skill-evals skills/commit-message     # one skill: a new or changed skill in a pull request
  uv run skill-evals                           # every skill: nightly, to catch model changes
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

import litellm
import opik
import yaml
from opik.evaluation.metrics import BaseMetric, Contains, Equals, RegexMatch
from opik.evaluation.metrics.score_result import ScoreResult
from opik.integrations.litellm import track_completion

PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME") or "coding-agent-skill-evals"
# WHY: some SDK steps (evaluate_experiment's scoring traces) only read the project from the environment.
os.environ["OPIK_PROJECT_NAME"] = PROJECT_NAME

# WHY: an unset GitHub Actions variable arrives as "", so fall back with `or`.
AGENT_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL") or "anthropic/claude-haiku-4-5-20251001"
# WHY: the judge can open the run's trace (every tool call and result) only for models the SDK lists, matched
# by bare name; a provider-prefixed name such as "anthropic/..." falls back to judging the output alone.
# Not Haiku: as a trace-reading judge it sometimes answers only the first assertion, which fails the run.
JUDGE_MODEL = "claude-sonnet-4-6"
EXECUTION_POLICY = {"runs_per_item": 3, "pass_threshold": 3}  # every run must pass
SKILLS_DIR = pathlib.Path(__file__).resolve().parent / "skills"
MAX_TURNS = 8

DRY_RUN = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))

OUTPUT_FIELDS = ("skills_loaded", "commands_run", "answer")
HEURISTICS = {"equals": Equals, "contains": Contains, "regex": RegexMatch}
TEST_KEYS = {"input", "tool_outputs", "assertions", "heuristics"}

completion = track_completion()(litellm.completion)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": (
                "Load the full instructions of a skill. "
                "Call it when the request matches the skill's description."
            ),
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the user's repository.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


def read_skill(folder: pathlib.Path) -> dict:
    text = (folder / "SKILL.md").read_text()
    _, frontmatter, body = text.split("---", 2)
    return {"folder": folder, "text": text, "body": body.strip(), **yaml.safe_load(frontmatter)}


@opik.track(type="tool")
def load_skill(skills: dict, name: str) -> str:
    return skills[name]["body"] if name in skills else f"There is no skill named {name}."


@opik.track(type="tool")
def run_command(command: str, tool_outputs: dict) -> str:
    # WHY: nothing is executed; a test's tool_outputs fake the result of any command containing the key.
    for match, output in tool_outputs.items():
        if match in command:
            return output
    return "Simulated environment: the command was recorded but not executed, so there is no output."


def run_agent(request: str, skills: dict, tool_outputs: dict) -> dict:
    """A minimal coding agent: it sees every skill's name and description, as real agents do."""
    catalogue = "\n".join(f"- {s['name']}: {s['description']}" for s in skills.values())
    system = (
        "You are a coding agent working in the user's repository.\n"
        f"Skills you can load:\n{catalogue}\n\n"
        "When a request matches a skill's description, load it with load_skill and follow it. "
        "Otherwise answer directly."
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": request}]
    skills_loaded, commands_run = [], []

    for _ in range(MAX_TURNS):
        message = completion(model=AGENT_MODEL, messages=messages, tools=TOOLS).choices[0].message
        messages.append(message)
        if not message.tool_calls:
            break
        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            if call.function.name == "load_skill":
                skills_loaded.append(args["name"])
                content = load_skill(skills, args["name"])
            else:
                commands_run.append(args["command"])
                content = run_command(args["command"], tool_outputs)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

    # WHY: what the agent did goes in the output, so any judge model and the heuristics can check it.
    return {
        "skills_loaded": "\n".join(skills_loaded),
        "commands_run": "\n".join(commands_run),
        "answer": message.content or "",
    }


def make_task(skills: dict):
    """The function run_tests calls once per test run. Swap run_agent here to test a real agent."""

    def task(item: dict) -> dict:
        return {
            "input": item["input"],
            "output": run_agent(item["input"], skills, item.get("tool_outputs") or {}),
        }

    return task


def git_commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:7]
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() or "local"


class Heuristics(BaseMetric):
    """Runs Opik's built-in heuristic metrics on output fields, as listed under a test's `heuristics:`."""

    def score(self, output: dict, heuristics: dict = None, **ignored) -> list:
        results = []
        for field, checks in (heuristics or {}).items():
            for kind, expected in checks.items():
                if kind == "regex":
                    r = RegexMatch(regex=expected, track=False).score(output=output[field])
                else:
                    r = HEURISTICS[kind](track=False).score(output=output[field], reference=expected)
                results.append(
                    ScoreResult(name=f"{field} {kind}", value=r.value, reason=f"expected {kind} {expected!r}")
                )
        return results


def check_evals(evals: dict) -> list:
    """Mistakes a skill author can make in evals.yaml, found without calling a model."""
    errors = []
    tests = evals.get("tests") or []
    if not tests:
        errors.append("no tests")
    for i, test in enumerate(tests, 1):
        if unknown := set(test) - TEST_KEYS:
            errors.append(f"test {i}: unknown keys {sorted(unknown)}")
        if not test.get("input"):
            errors.append(f"test {i}: no input")
        if not (test.get("assertions") or test.get("heuristics") or evals.get("assertions")):
            errors.append(f"test {i}: nothing to check")
        for field, checks in (test.get("heuristics") or {}).items():
            if field not in OUTPUT_FIELDS:
                errors.append(f"test {i}: heuristic on unknown field {field!r}, use one of {OUTPUT_FIELDS}")
            for kind, expected in checks.items():
                if kind not in HEURISTICS:
                    errors.append(f"test {i}: unknown heuristic {kind!r}, use one of {sorted(HEURISTICS)}")
                elif kind == "regex":
                    try:
                        re.compile(expected)
                    except re.error as e:
                        errors.append(f"test {i}: invalid regex {expected!r}: {e}")
    return errors


def dry_run(skill: dict) -> bool:
    evals = yaml.safe_load((skill["folder"] / "evals.yaml").read_text())
    errors = check_evals(evals)
    tests = evals.get("tests") or []
    print(
        f"[DRY RUN] {skill['name']}: would sync test suite skill-{skill['name']} with {len(tests)} tests "
        f"and run each {EXECUTION_POLICY['runs_per_item']} times (agent {AGENT_MODEL}, judge {JUDGE_MODEL})"
    )
    for name in evals.get("assertions") or []:
        print(f"  every test: {name}")
    for test in tests:
        checks = len(test.get("assertions") or []) + sum(
            len(c) for c in (test.get("heuristics") or {}).values()
        )
        print(f"  - {str(test.get('input', '')).splitlines()[0][:70]}  (checks: {checks})")
    for error in errors:
        print(f"  ERROR {error}")
    return not errors


def sync_suite(name: str, evals: dict):
    """Make the Opik test suite match evals.yaml. Opik versions the suite on every change."""
    suite = opik.Opik().get_or_create_test_suite(
        name=f"skill-{name}",
        project_name=PROJECT_NAME,
        global_assertions=evals.get("assertions", []),
        global_execution_policy=EXECUTION_POLICY,
    )
    suite.update_test_settings(
        global_assertions=evals.get("assertions", []), global_execution_policy=EXECUTION_POLICY
    )
    # WHY: tool_outputs and heuristics live in the item's data for the task and metrics to read.
    wanted = [
        {
            "data": {
                "input": t["input"],
                "tool_outputs": t.get("tool_outputs", {}),
                "heuristics": t.get("heuristics", {}),
            },
            "assertions": t.get("assertions", []),
        }
        for t in evals["tests"]
    ]
    current = [{"data": i["data"], "assertions": i["assertions"]} for i in suite.get_items()]
    key = lambda items: sorted(json.dumps(i, sort_keys=True) for i in items)  # noqa: E731
    if key(current) != key(wanted):
        suite.clear()
        suite.insert(wanted)
    return suite


def evaluate_skill(skill: dict, skills: dict) -> bool:
    evals = yaml.safe_load((skill["folder"] / "evals.yaml").read_text())
    if errors := check_evals(evals):
        print(f"{skill['name']}: evals.yaml has errors: {'; '.join(errors)}")
        return False
    path = str(skill["folder"].relative_to(SKILLS_DIR.parent))
    commit = git_commit()

    # WHY: a new Prompt Library version is created when SKILL.md or this metadata changes, so per-run
    # values such as the git commit go in experiment_config instead.
    prompt = opik.Opik().create_prompt(
        name=f"skill-{skill['name']}",
        prompt=skill["text"],
        metadata={"path": path},
        project_name=PROJECT_NAME,
    )
    suite = sync_suite(skill["name"], evals)

    result = opik.run_tests(
        test_suite=suite,
        task=make_task(skills),
        prompts=[prompt],
        model=JUDGE_MODEL,
        experiment_name=f"{skill['name']} @ {commit}",
        experiment_config={
            "skill": skill["name"],
            "skill_path": path,
            "skill_version": prompt.commit,
            "git_commit": commit,
            "agent_model": AGENT_MODEL,
            "judge_model": JUDGE_MODEL,
            "harness": "simulated",
        },
        experiment_tags=["skill-evals"],
        generate_report=False,
        verbose=1,
    )
    summary = f"{skill['name']}: {result.items_passed}/{result.items_total} tests passed"

    failed = []
    if any(t.get("heuristics") for t in evals["tests"]):
        # WHY: test suites only run judge assertions, so heuristics score the same runs in a second step.
        # Any failure on any run fails the skill, matching the suite's "every run must pass" policy.
        scores = opik.evaluate_experiment(
            experiment_name=result.experiment_name,
            experiment_id=result.experiment_id,
            scoring_metrics=[Heuristics(name="heuristics")],
            project_name=PROJECT_NAME,
            verbose=0,
        )
        checks = [s for t in scores.test_results for s in t.score_results]
        failed = [s for s in checks if s.value != 1]
        summary += f", heuristics {len(checks) - len(failed)}/{len(checks)} checks passed"

    print(f"{summary}  {result.experiment_url}")
    for s in failed:
        print(f"  heuristic failed: {s.name} ({s.reason})")
    return result.all_items_passed and not failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="*", type=pathlib.Path, help="Skill folders to test (default: all).")
    parser.add_argument(
        "--dry-run", action="store_true", help="Check evals.yaml files; call no model, send nothing."
    )
    args = parser.parse_args()

    skills = {
        s["name"]: s
        for s in (read_skill(f) for f in sorted(SKILLS_DIR.iterdir()) if (f / "SKILL.md").exists())
    }
    selected = [read_skill(f.resolve()) for f in args.folders] or list(skills.values())

    if args.dry_run or DRY_RUN:
        if not args.dry_run:
            print("OPIK_API_KEY / OPIK_WORKSPACE not set, running in DRY_RUN.", file=sys.stderr)
        return 0 if all([dry_run(s) for s in selected]) else 1
    return 0 if all([evaluate_skill(s, skills) for s in selected]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
