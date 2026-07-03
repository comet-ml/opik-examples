from __future__ import annotations

import sys
from pathlib import Path

from entry_rules import (
    validate_code_uses_opik,
    validate_folder_name,
    validate_meta,
    validate_no_secrets,
    validate_proof,
    validate_readme,
)

COMMUNITY_DIR = Path(__file__).resolve().parent.parent
RESERVED_DIRS = {"_ci", "templates"}


def discover_entries(community_dir: Path) -> list[Path]:
    return [
        child
        for child in sorted(community_dir.iterdir())
        if child.is_dir() and child.name not in RESERVED_DIRS
    ]


def check_entry(entry: Path) -> list[str]:
    errors: list[str] = []
    errors += validate_folder_name(entry)
    errors += validate_meta(entry)
    errors += validate_readme(entry)
    errors += validate_proof(entry)
    errors += validate_no_secrets(entry)
    errors += validate_code_uses_opik(entry)
    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        entries = [Path(a) for a in args]
    else:
        entries = discover_entries(COMMUNITY_DIR)

    if not entries:
        print("No community entries to check.")
        return 0

    all_errors: list[str] = []
    for entry in entries:
        entry_errors = check_entry(entry)
        if entry_errors:
            all_errors.extend(entry_errors)
        else:
            print(f"OK  {entry.name}")

    if all_errors:
        print("\nCommunity entry check failed:")
        for error in all_errors:
            print(f"  - {error}")
        return 1

    print("\nAll community entries passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
