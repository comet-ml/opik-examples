from __future__ import annotations

import sys
from pathlib import Path

from project_rules import load_projects, validate_projects

COMMUNITY_DIR = Path(__file__).resolve().parent.parent
PROJECTS_FILE = COMMUNITY_DIR / "projects.yaml"


def check_projects(path: Path) -> list[str]:
    projects, errors = load_projects(path)
    if errors:
        return errors
    return validate_projects(projects)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else PROJECTS_FILE

    errors = check_projects(path)
    if errors:
        print("Community projects check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    projects, _ = load_projects(path)
    print(f"OK  {len(projects)} community project(s) validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
