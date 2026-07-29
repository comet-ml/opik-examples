import re
from pathlib import Path

import pytest
from conftest import make_project, write_projects

from build_index import check_index, load_entries, render_index, write_index


def _unescaped_pipe_count(row: str) -> int:
    return len(re.findall(r"(?<!\\)\|", row))


def test_load_entries_reads_projects_file(tmp_path: Path):
    write_projects(tmp_path)
    entries = load_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["title"] == "Real-time support agent with Opik tracing"
    assert entries[0]["repo"] == "https://github.com/jane-doe/support-agent"


def test_load_entries_sorts_by_title_casefold(tmp_path: Path):
    write_projects(
        tmp_path,
        projects=[
            make_project(title="zeta agent", repo="https://github.com/a/zeta"),
            make_project(title="Alpha agent", repo="https://github.com/a/alpha"),
        ],
    )
    titles = [e["title"] for e in load_entries(tmp_path)]
    assert titles == ["Alpha agent", "zeta agent"]


def test_load_entries_raises_on_invalid_projects_file(tmp_path: Path):
    write_projects(tmp_path, projects=[{"title": "x"}])
    with pytest.raises(ValueError, match="invalid projects.yaml"):
        load_entries(tmp_path)


def test_render_index_links_title_to_author_repo(tmp_path: Path):
    write_projects(tmp_path)
    out = render_index(load_entries(tmp_path))
    assert (
        "[Real-time support agent with Opik tracing]"
        "(https://github.com/jane-doe/support-agent)" in out
    )
    assert "[@jane-doe](https://github.com/jane-doe)" in out
    assert "community-contributed" in out.lower()


def test_render_index_has_three_columns(tmp_path: Path):
    write_projects(tmp_path)
    out = render_index(load_entries(tmp_path))
    assert "| Project | Description | Author |" in out


def test_render_index_empty_has_no_entries_note():
    out = render_index([])
    assert "no community contributions yet" in out.lower()


def test_write_then_check_roundtrips(tmp_path: Path):
    write_projects(tmp_path)
    write_index(tmp_path)
    assert (tmp_path / "README.md").is_file()
    assert check_index(tmp_path) is True


def test_check_index_detects_stale(tmp_path: Path):
    write_projects(tmp_path)
    (tmp_path / "README.md").write_text("# stale\n")
    assert check_index(tmp_path) is False


def test_pipe_in_description_is_escaped_in_table_row(tmp_path: Path):
    write_projects(
        tmp_path,
        projects=[make_project(description="Handles A | B and C | D cases")],
    )
    out = render_index(load_entries(tmp_path))
    table_line = next(line for line in out.splitlines() if line.startswith("| [Real"))
    assert "A \\| B and C \\| D" in table_line
    # 3 columns means 4 unescaped pipe delimiters (leading + trailing +
    # 2 separators); escaped pipes must not be miscounted as separators.
    assert _unescaped_pipe_count(table_line) == 4
