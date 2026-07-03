from pathlib import Path

from conftest import write_entry

from entry_rules import validate_meta, validate_proof, validate_readme


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


def test_valid_readme_has_no_errors(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert validate_readme(entry) == []


def test_missing_readme_is_error(tmp_path: Path):
    entry = tmp_path / "no_readme"
    entry.mkdir()
    assert any("README.md" in e for e in validate_readme(entry))


def test_missing_section_is_error(tmp_path: Path):
    readme = "# Title\n\n## What I built\nStuff.\n\n## Problem it solves\nX.\n"
    entry = write_entry(tmp_path, readme=readme)
    errors = validate_readme(entry)
    assert any("What I learned" in e for e in errors)
    assert any("How I used Opik" in e for e in errors)


def test_placeholder_body_is_error(tmp_path: Path):
    readme = (
        "# T\n\n## What I built\nTODO\n\n## Problem it solves\nX.\n\n"
        "## What I learned\nY.\n\n## How I used Opik\nZ.\n"
    )
    entry = write_entry(tmp_path, readme=readme)
    assert any("What I built" in e for e in validate_readme(entry))


def test_empty_section_body_is_error(tmp_path: Path):
    readme = (
        "# T\n\n## What I built\n\n## Problem it solves\nX.\n\n"
        "## What I learned\nY.\n\n## How I used Opik\nZ.\n"
    )
    entry = write_entry(tmp_path, readme=readme)
    assert any("What I built" in e for e in validate_readme(entry))


def test_valid_proof_has_no_errors(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert validate_proof(entry) == []


def test_missing_png_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, include_png=False)
    assert any("opik-proof.png" in e for e in validate_proof(entry))


def test_png_not_referenced_is_error(tmp_path: Path):
    readme = (
        "# T\n\n## What I built\nA.\n\n## Problem it solves\nB.\n\n"
        "## What I learned\nC.\n\n## How I used Opik\nNo image here.\n"
    )
    entry = write_entry(tmp_path, readme=readme)
    assert any("referenced" in e.lower() for e in validate_proof(entry))
