"""Files that are deliberate copies must stay identical: the runbook wrappers, and the sticky-comment
script shared by the workflow template and the repo selftest."""

from pathlib import Path

import yaml

GUIDE = Path(__file__).resolve().parents[1]
AGENT = GUIDE / "agent"


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        text = text.split("---\n", 2)[2]
    return text.strip()


def test_host_wrappers_match_runbook_body() -> None:
    runbook = _body(AGENT / "opik-eval-loop.md")
    assert _body(AGENT / "cursor" / "opik-eval-loop.mdc") == runbook
    assert _body(AGENT / "claude" / "opik-eval-loop" / "SKILL.md") == runbook


def _step_scripts(path: Path) -> dict[str, str]:
    steps = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]["eval"]["steps"]
    return {s["name"]: s["with"]["script"] for s in steps if "script" in s.get("with", {})}


def test_selftest_comment_script_matches_template() -> None:
    selftest = GUIDE.parents[1] / ".github" / "workflows" / "eval-in-ci-selftest.yml"
    if not selftest.is_file():  # the guide is copied into other repos without the selftest
        return
    template = _step_scripts(GUIDE / "github" / "opik-eval.yml")["Post sticky PR comment"]
    ours = _step_scripts(selftest)["Post sticky PR comment"].replace("guides/eval_in_ci/", "")
    assert ours == template
