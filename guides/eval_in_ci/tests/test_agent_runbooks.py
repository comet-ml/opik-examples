"""The Cursor rule and Claude skill must carry the runbook verbatim, so a change in one lands in all."""

from pathlib import Path

AGENT = Path(__file__).resolve().parents[1] / "agent"


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        text = text.split("---\n", 2)[2]
    return text.strip()


def test_host_wrappers_match_runbook_body() -> None:
    runbook = _body(AGENT / "opik-eval-loop.md")
    assert _body(AGENT / "cursor" / "opik-eval-loop.mdc") == runbook
    assert _body(AGENT / "claude" / "opik-eval-loop" / "SKILL.md") == runbook
