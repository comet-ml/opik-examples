from __future__ import annotations

import re
from pathlib import Path

import yaml

REQUIRED_FIELDS = ["title", "description", "author", "repo"]
ALLOWED_FIELDS = set(REQUIRED_FIELDS)
MAX_DESCRIPTION_LENGTH = 250

# GitHub usernames/orgs: alphanumeric and hyphens, no leading/trailing hyphen, max 39 chars.
_GITHUB_HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def load_projects(path: Path) -> tuple[list, list[str]]:
    if not path.is_file():
        return [], [f"{path.name}: file not found at {path}"]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [], [f"{path.name}: not valid YAML ({exc})"]
    if data is None:
        return [], []
    if not isinstance(data, list):
        return [], [f"{path.name}: must be a top-level YAML list of projects"]
    return data, []


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def validate_project(item: object, index: int) -> list[str]:
    label = f"projects.yaml item {index + 1}"
    if not isinstance(item, dict):
        return [f"{label}: must be a mapping with fields {REQUIRED_FIELDS}"]

    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        value = item.get(field)
        if not _nonempty_str(value):
            errors.append(f"{label}: field '{field}' is required and must be a non-empty string")
        elif "\n" in str(value) or "\r" in str(value):
            # WHY: a newline inside any field splits the generated markdown table row.
            errors.append(f"{label}: field '{field}' must be a single line")

    unknown = sorted(set(item) - ALLOWED_FIELDS)
    if unknown:
        errors.append(f"{label}: unknown field(s) {unknown} — allowed fields are {REQUIRED_FIELDS}")

    repo = item.get("repo")
    if _nonempty_str(repo):
        repo_str = str(repo).strip()
        if not repo_str.startswith(("http://", "https://")) or any(c.isspace() for c in repo_str):
            errors.append(f"{label}: 'repo' must be an http(s) URL without whitespace")

    author = item.get("author")
    if _nonempty_str(author) and not _GITHUB_HANDLE_RE.match(str(author).strip()):
        errors.append(
            f"{label}: 'author' must be a bare GitHub handle "
            f"(letters/digits/hyphens, no leading '@' or URL)"
        )

    description = item.get("description")
    if _nonempty_str(description) and len(str(description).strip()) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"{label}: 'description' must be at most {MAX_DESCRIPTION_LENGTH} characters "
            f"(1-2 sentences) to keep the table scannable"
        )

    return errors


def validate_projects(projects: list) -> list[str]:
    errors: list[str] = []
    seen_titles: dict[str, int] = {}
    seen_repos: dict[str, int] = {}

    for index, item in enumerate(projects):
        errors.extend(validate_project(item, index))
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        if _nonempty_str(title):
            key = str(title).strip().casefold()
            if key in seen_titles:
                errors.append(
                    f"projects.yaml item {index + 1}: duplicate title "
                    f"(already used by item {seen_titles[key] + 1})"
                )
            else:
                seen_titles[key] = index

        repo = item.get("repo")
        if _nonempty_str(repo):
            key = str(repo).strip().rstrip("/").casefold()
            if key in seen_repos:
                errors.append(
                    f"projects.yaml item {index + 1}: duplicate repo "
                    f"(already used by item {seen_repos[key] + 1})"
                )
            else:
                seen_repos[key] = index

    return errors
