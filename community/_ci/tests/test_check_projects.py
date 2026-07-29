from pathlib import Path

from conftest import make_project, write_projects

from check_projects import COMMUNITY_DIR, PROJECTS_FILE, check_projects, main


def test_valid_file_passes(tmp_path: Path):
    path = write_projects(tmp_path)
    assert check_projects(path) == []


def test_check_aggregates_multiple_failures(tmp_path: Path):
    path = write_projects(
        tmp_path,
        projects=[make_project(title=None, repo="not-a-url")],
    )
    errors = check_projects(path)
    assert any("'title'" in e for e in errors)
    assert any("'repo'" in e for e in errors)


def test_main_returns_zero_for_valid_file(tmp_path: Path):
    path = write_projects(tmp_path)
    assert main([str(path)]) == 0


def test_main_returns_one_for_invalid_file(tmp_path: Path):
    path = write_projects(tmp_path, projects=[{"title": "x"}])
    assert main([str(path)]) == 1


def test_main_returns_one_for_missing_file(tmp_path: Path):
    assert main([str(tmp_path / "projects.yaml")]) == 1


def test_default_path_points_at_repo_projects_file():
    assert PROJECTS_FILE == COMMUNITY_DIR / "projects.yaml"
