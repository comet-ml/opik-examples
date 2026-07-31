from conftest import make_project

from check_projects import PROJECTS_FILE
from project_rules import load_projects, validate_projects


def test_make_project_default_is_valid():
    assert validate_projects([make_project()]) == []


def test_make_project_can_delete_a_field():
    assert "title" not in make_project(title=None)


def test_repo_projects_file_is_valid():
    projects, errors = load_projects(PROJECTS_FILE)
    assert errors == []
    assert validate_projects(projects) == []
    assert len(projects) >= 1
