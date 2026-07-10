from pathlib import Path

from conftest import write_entry

from check_entry import check_entry, discover_entries, main


def test_valid_entry_passes(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert check_entry(entry) == []


def test_check_entry_aggregates_multiple_failures(tmp_path: Path):
    entry = write_entry(tmp_path, slug="BadName", meta={"title": None}, include_png=False)
    errors = check_entry(entry)
    assert any("title" in e for e in errors)
    assert any("opik-proof.png" in e for e in errors)
    assert any("folder name" in e.lower() for e in errors)


def test_discover_skips_reserved_dirs(tmp_path: Path):
    write_entry(tmp_path, slug="jane_agent")
    (tmp_path / "_ci").mkdir()
    (tmp_path / "_ci" / "meta.yaml").write_text("title: x\n")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "meta.yaml").write_text("title: x\n")
    found = {p.name for p in discover_entries(tmp_path)}
    assert found == {"jane_agent"}


def test_discover_includes_dir_without_meta_yaml(tmp_path: Path):
    entry = write_entry(tmp_path, slug="no_meta_here")
    (entry / "meta.yaml").unlink()
    found = {p.name for p in discover_entries(tmp_path)}
    assert "no_meta_here" in found


def test_check_entry_flags_missing_meta_yaml(tmp_path: Path):
    entry = write_entry(tmp_path, slug="no_meta_here")
    (entry / "meta.yaml").unlink()
    errors = check_entry(entry)
    assert any("missing meta.yaml" in e for e in errors)


def test_main_no_args_returns_one_when_entry_missing_meta_yaml(tmp_path: Path, monkeypatch):
    entry = write_entry(tmp_path, slug="no_meta_here")
    (entry / "meta.yaml").unlink()
    import check_entry as check_entry_module

    monkeypatch.setattr(check_entry_module, "COMMUNITY_DIR", tmp_path)
    assert main([]) == 1


def test_main_returns_zero_for_valid_entry(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert main([str(entry)]) == 0


def test_main_returns_one_for_invalid_entry(tmp_path: Path):
    entry = write_entry(tmp_path, include_png=False)
    assert main([str(entry)]) == 1
