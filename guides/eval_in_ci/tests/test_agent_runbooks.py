"""The runbook wrappers are deliberate copies of the runbook and must stay identical."""

from pathlib import Path

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


def test_runbook_has_no_research_notes_or_stale_names() -> None:
    text = _body(AGENT / "opik-eval-loop.md")
    for banned in ("backlog", "not yet been observed", "'error_info']", "example_task", "scenario_agent"):
        assert banned not in text, banned
    for needed in (
        "prompts/system.txt",
        "examples/eval_in_ci/prompts/system.txt",
        ".github/workflows/opik-eval.yml",
        ".opik/**",
        "examples/eval_in_ci/opik-release-policy.yaml",
        "examples/eval_in_ci/.opik/**",
        "https://www.comet.com/docs/opik/mcp-server",
        "https://www.comet.com/docs/opik/mcp-server/use-cases",
        "https://www.comet.com/docs/opik/mcp-server/advanced-setup",
        "exploration goes through the Opik MCP server when it is connected",
        "uv run python run_eval.py digest --experiment",
        "is a hold unless the policy sets `test_suite: skip`",
        "Returning the expected plan is cheating",
    ):
        assert needed in text, needed
    assert "python examples/eval_in_ci/run_eval.py" not in text
