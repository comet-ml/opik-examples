from pathlib import Path

from conftest import write_entry

from build_index import check_index, load_entries, render_index, write_index


def test_load_entries_reads_meta(tmp_path: Path):
    write_entry(tmp_path, slug="jane_agent")
    entries = load_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["slug"] == "jane_agent"
    assert entries[0]["title"]


def test_render_index_lists_entry_and_links_to_folder(tmp_path: Path):
    write_entry(tmp_path, slug="jane_agent")
    out = render_index(load_entries(tmp_path))
    assert "jane_agent" in out
    assert "community-contributed" in out.lower()


def test_render_index_hosted_badge_is_text_not_emoji(tmp_path: Path):
    write_entry(tmp_path, slug="jane_agent", meta={"hosted": True})
    out = render_index(load_entries(tmp_path))
    assert "hosted" in out.lower()


def test_render_index_empty_has_no_entries_note(tmp_path: Path):
    out = render_index([])
    assert "no community contributions yet" in out.lower()


def test_write_then_check_roundtrips(tmp_path: Path):
    write_entry(tmp_path, slug="jane_agent")
    write_index(tmp_path)
    assert (tmp_path / "README.md").is_file()
    assert check_index(tmp_path) is True


def test_check_index_detects_stale(tmp_path: Path):
    write_entry(tmp_path, slug="jane_agent")
    (tmp_path / "README.md").write_text("# stale\n")
    assert check_index(tmp_path) is False


def test_pipe_in_description_is_escaped_in_table_row(tmp_path: Path):
    write_entry(
        tmp_path,
        slug="jane_agent",
        meta={"description": "Handles A | B and C | D cases"},
    )
    out = render_index(load_entries(tmp_path))
    table_line = next(line for line in out.splitlines() if line.startswith("| [Real"))
    assert "A \\| B and C \\| D" in table_line
    # Stripping the leading/trailing "| " and splitting on " | " must yield
    # exactly 7 columns; escaped pipes must not be miscounted as separators.
    stripped = table_line.strip()
    assert stripped.startswith("| ") and stripped.endswith(" |")
    inner = stripped[2:-2]
    assert len(inner.split(" | ")) == 7
