"""The README follows the repo's required sections and names what the code actually uses."""

import re
from pathlib import Path

import config

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

MCP_DOCS = (
    "https://www.comet.com/docs/opik/mcp-server",
    "https://www.comet.com/docs/opik/mcp-server/use-cases",
    "https://www.comet.com/docs/opik/mcp-server/advanced-setup",
)


def test_required_sections() -> None:
    headings = ("## What this does", "## Prerequisites", "## Running it", "## How it works")
    positions = []
    for heading in headings:
        match = re.search(rf"^{re.escape(heading)}$", README, flags=re.MULTILINE)
        assert match, heading
        positions.append(match.start())
    assert positions == sorted(positions)


# WHY: house style is plain keyboard characters (no typographic dashes, arrows, quotes or ticks).
def test_plain_keyboard_characters() -> None:
    found = sorted({ch for ch in README if ord(ch) > 127})
    assert not found, found


def test_no_stale_names() -> None:
    for stale in (
        "example_task",
        "scenario_agent",
        "run_label",
        "staging",
        "`development`",
        "TypeScript",
        "backlog",
    ):
        assert stale not in README, stale


def test_names_match_config() -> None:
    for name in (
        config.DATASET_NAME,
        config.TEST_SUITE_NAME,
        config.ONLINE_RULE_NAME,
        config.PROMPT_NAME,
        config.ENV_PRODUCTION,
    ):
        assert name in README, name


def test_mcp_docs_links_present() -> None:
    for url in MCP_DOCS:
        assert re.search(rf"{re.escape(url)}(?![\w/-])", README), url


# WHY: the sample must sit right under its heading and start with the sticky-comment marker.
def test_sample_comment_present() -> None:
    heading = re.search(r"^#{2,4} What you get$", README, flags=re.MULTILINE)
    assert heading, "missing 'What you get' heading"
    rest = README[heading.end() :]
    fence = re.search(r"^```[\w-]*\n(.*)$", rest, flags=re.MULTILINE)
    assert fence, "no fenced block after 'What you get'"
    assert not re.search(r"^#", rest[: fence.start()], flags=re.MULTILINE), "fence is under another heading"
    assert fence.group(1) == "<!-- opik-eval -->"


# WHY: these modules write descriptions clients see in Opik, so they must use the current names too.
def test_no_stale_names_in_sources() -> None:
    guide = Path(__file__).resolve().parents[1]
    for module in ("setup_opik.py", "scenarios.py", "planner.py", "config.py"):
        text = (guide / module).read_text(encoding="utf-8")
        for stale in ("staging", "run label", "strong.txt"):
            assert stale not in text, f"{module}: {stale}"
