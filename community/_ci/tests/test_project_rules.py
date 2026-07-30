from pathlib import Path

from conftest import make_project, write_projects

from project_rules import load_projects, validate_project, validate_projects


def test_valid_project_passes():
    assert validate_project(make_project(), 0) == []


def test_missing_required_fields_are_reported():
    errors = validate_project({}, 0)
    for field in ("title", "description", "author", "repo"):
        assert any(f"'{field}'" in e for e in errors)


def test_non_mapping_item_is_reported():
    errors = validate_project("just a string", 0)
    assert len(errors) == 1
    assert "must be a mapping" in errors[0]


def test_unknown_fields_are_rejected():
    errors = validate_project(make_project(tags=["agent"]), 0)
    assert any("unknown field" in e.lower() and "tags" in e for e in errors)


def test_repo_must_be_http_url():
    errors = validate_project(make_project(repo="git@github.com:jane/agent.git"), 0)
    assert any("'repo' must be an http(s) URL" in e for e in errors)


def test_repo_with_whitespace_is_rejected():
    errors = validate_project(make_project(repo="https://github.com/jane/my repo"), 0)
    assert any("'repo'" in e for e in errors)


def test_multiline_fields_are_rejected():
    for field in ("title", "description", "repo"):
        errors = validate_project(make_project(**{field: "line one\nline two"}), 0)
        assert any("must be a single line" in e for e in errors), field


def test_author_must_be_bare_github_handle():
    for bad in ("@jane-doe", "https://github.com/jane-doe", "jane doe", "jane-", "-jane"):
        errors = validate_project(make_project(author=bad), 0)
        assert any("'author'" in e for e in errors), bad


def test_description_length_is_capped():
    errors = validate_project(make_project(description="x" * 251), 0)
    assert any("at most 250" in e for e in errors)
    assert validate_project(make_project(description="x" * 250), 0) == []


def test_duplicate_titles_are_rejected():
    projects = [make_project(), make_project(repo="https://github.com/other/repo")]
    errors = validate_projects(projects)
    assert any("duplicate title" in e for e in errors)


def test_duplicate_repos_are_rejected_ignoring_case_and_trailing_slash():
    projects = [
        make_project(),
        make_project(
            title="Another project",
            repo="https://github.com/Jane-Doe/Support-Agent/",
        ),
    ]
    errors = validate_projects(projects)
    assert any("duplicate repo" in e for e in errors)


def test_error_messages_use_one_based_item_numbers():
    projects = [make_project(), {"title": "x"}]
    errors = validate_projects(projects)
    assert any(e.startswith("projects.yaml item 2:") for e in errors)


def test_load_projects_missing_file(tmp_path: Path):
    projects, errors = load_projects(tmp_path / "projects.yaml")
    assert projects == []
    assert any("file not found" in e for e in errors)


def test_load_projects_invalid_yaml(tmp_path: Path):
    path = write_projects(tmp_path, raw="- title: [unclosed\n")
    projects, errors = load_projects(path)
    assert projects == []
    assert any("not valid YAML" in e for e in errors)


def test_load_projects_rejects_mapping_at_top_level(tmp_path: Path):
    path = write_projects(tmp_path, raw="title: not a list\n")
    projects, errors = load_projects(path)
    assert projects == []
    assert any("top-level YAML list" in e for e in errors)


def test_load_projects_empty_file_is_ok(tmp_path: Path):
    path = write_projects(tmp_path, raw="# no projects yet\n")
    projects, errors = load_projects(path)
    assert projects == []
    assert errors == []
