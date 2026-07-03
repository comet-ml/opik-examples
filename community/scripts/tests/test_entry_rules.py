from pathlib import Path

from conftest import write_entry

from entry_rules import validate_meta


def test_valid_meta_has_no_errors(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert validate_meta(entry) == []


def test_missing_meta_file_is_error(tmp_path: Path):
    entry = tmp_path / "no_meta"
    entry.mkdir()
    errors = validate_meta(entry)
    assert any("meta.yaml" in e for e in errors)


def test_missing_required_field_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"title": None})
    assert any("title" in e for e in validate_meta(entry))


def test_empty_required_field_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"description": "  "})
    assert any("description" in e for e in validate_meta(entry))


def test_links_must_have_one_http_value(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"links": {"repo": "not-a-url"}})
    assert any("link" in e.lower() for e in validate_meta(entry))


def test_invalid_platform_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"opik_platform": "on-prem"})
    assert any("opik_platform" in e for e in validate_meta(entry))


def test_hosted_must_be_bool(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"hosted": "yes"})
    assert any("hosted" in e for e in validate_meta(entry))


def test_tags_must_be_list(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"tags": "agent"})
    assert any("tags" in e for e in validate_meta(entry))


def test_malformed_yaml_is_reported(tmp_path: Path):
    entry = tmp_path / "bad_yaml"
    entry.mkdir()
    (entry / "meta.yaml").write_text("title: [unclosed\n")
    errors = validate_meta(entry)
    assert any("meta.yaml" in e for e in errors)
