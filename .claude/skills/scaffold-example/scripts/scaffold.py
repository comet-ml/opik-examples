#!/usr/bin/env python3
"""Scaffold a new Opik example by copying and renaming a canonical template.

Two templates live under `templates/`:

  - `use-case-template`  — a full uv + Typer package wired through the whole Opik loop
                           (sentinels `example_use_case` / `example-use-case`). Default.
  - `script-template`    — a single-file argparse utility script
                           (sentinels `example_script` / `example-script`).

Each template is a real, runnable project under a sentinel identity. This script copies the
chosen template to the target bucket and rewrites those sentinels to the new name — a pure
identifier rename, no template language. Run it, then fill in the TODO stubs.

  python scaffold.py my_use_case --description "..."                          # use-case (default)
  python scaffold.py my_script --bucket scripts --template script-template --description "..."
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

# Templates this scaffolder can stamp. `kind` selects how the module is renamed and wired:
#   package -> rename the src/<sentinel>/ dir; entry point is <pkg>.cli:main
#   script  -> rename the <sentinel>.py file;  entry point is <pkg>:main
TEMPLATES = {
    "use-case-template": {
        "dir": ("templates", "use-case-template"),
        "pkg_sentinel": "example_use_case",  # snake_case: src/ package / import name
        "project_sentinel": "example-use-case",  # kebab-case: project name + CLI command
        "kind": "package",
    },
    "script-template": {
        "dir": ("templates", "script-template"),
        "pkg_sentinel": "example_script",  # snake_case: the .py module name
        "project_sentinel": "example-script",  # kebab-case: project name + CLI command
        "kind": "script",
    },
}
DEFAULT_TEMPLATE = "use-case-template"

EXCLUDE = shutil.ignore_patterns(
    ".venv", "uv.lock", "__pycache__", "*.pyc", ".ruff_cache", ".env", "*.log", ".tmp", "chroma_db"
)


def to_snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip().lower()).strip("_")
    if not s:
        raise ValueError(f"cannot derive a package name from {name!r}")
    if s[0].isdigit():
        s = f"x_{s}"
    return s


def to_kebab(snake: str) -> str:
    return snake.replace("_", "-")


def is_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, OSError):
        return False


def resolve_template(tmpl_arg: str | None, repo_root: Path) -> tuple[Path, dict]:
    """Resolve --template to a (dir, spec) pair. Accepts a registry name or an explicit path."""
    tmpl_arg = tmpl_arg or DEFAULT_TEMPLATE
    if tmpl_arg in TEMPLATES:
        spec = TEMPLATES[tmpl_arg]
        return repo_root.joinpath(*spec["dir"]), spec
    # Explicit path: match by directory name, else infer kind from structure.
    path = Path(tmpl_arg).resolve()
    if path.name in TEMPLATES:
        return path, TEMPLATES[path.name]
    kind = "package" if (path / "src").is_dir() else "script"
    spec = next(s for s in TEMPLATES.values() if s["kind"] == kind)
    return path, spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new Opik example from a templates/ template.")
    parser.add_argument("name", help="Example name, e.g. 'support_ticket_summarizer' or 'Trace Dumper'.")
    parser.add_argument("--description", default=None, help="One-line description for pyproject.toml.")
    parser.add_argument("--bucket", default="use-cases", help="Target bucket dir (default: use-cases).")
    parser.add_argument("--command", default=None, help="CLI command name (default: kebab-cased name).")
    parser.add_argument("--repo-root", default=None, help="Repo root (default: inferred from this script).")
    parser.add_argument(
        "--template",
        default=None,
        help=f"Template: a registry name ({', '.join(TEMPLATES)}) or a path. Default: {DEFAULT_TEMPLATE}.",
    )
    parser.add_argument("--dest-root", default=None, help="Where <bucket>/ lives (default: repo root).")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[4]
    template, spec = resolve_template(args.template, repo_root)
    dest_root = Path(args.dest_root).resolve() if args.dest_root else repo_root

    pkg_sentinel = spec["pkg_sentinel"]
    project_sentinel = spec["project_sentinel"]
    kind = spec["kind"]

    pkg = to_snake(args.name)
    kebab = to_kebab(pkg)
    command = args.command or kebab

    if not template.is_dir():
        print(f"error: template not found at {template}", file=sys.stderr)
        return 1

    dest = dest_root / args.bucket / pkg
    if dest.exists():
        print(f"error: {dest} already exists — refusing to overwrite.", file=sys.stderr)
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, dest, ignore=EXCLUDE)

    # Rename the package dir (package kind) or the module file (script kind).
    if kind == "package":
        pkg_dir = dest / "src" / pkg_sentinel
        if pkg_dir.is_dir():
            pkg_dir.rename(dest / "src" / pkg)
    else:
        mod_file = dest / f"{pkg_sentinel}.py"
        if mod_file.is_file():
            mod_file.rename(dest / f"{pkg}.py")

    # Rewrite sentinels in every text file. Snake and kebab sentinels don't overlap
    # (underscore vs hyphen), so independent replacement is safe.
    for path in dest.rglob("*"):
        if not path.is_file() or not is_text(path):
            continue
        text = path.read_text(encoding="utf-8")
        new = text.replace(pkg_sentinel, pkg).replace(project_sentinel, kebab)
        if new != text:
            path.write_text(new, encoding="utf-8")

    # Custom command: fix the [project.scripts] key (kebab -> command) without touching the
    # project name, which also kebab-matched above. Entry target differs by kind.
    if command != kebab:
        entry = f"{pkg}.cli:main" if kind == "package" else f"{pkg}:main"
        pyproject = dest / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        text = text.replace(f'{kebab} = "{entry}"', f'{command} = "{entry}"')
        pyproject.write_text(text, encoding="utf-8")

        # run.sh invokes the CLI by the kebab name (from the sentinel rewrite); point it
        # at the overridden command so `bash run.sh` matches [project.scripts].
        run_sh = dest / "run.sh"
        if run_sh.is_file():
            text = run_sh.read_text(encoding="utf-8")
            text = text.replace(f"uv run {kebab}", f"uv run {command}")
            run_sh.write_text(text, encoding="utf-8")

    # Description.
    if args.description:
        pyproject = dest / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        text = re.sub(
            r'^description = ".*"$',
            f'description = "{args.description}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        pyproject.write_text(text, encoding="utf-8")

    rel = dest.relative_to(dest_root) if dest.is_relative_to(dest_root) else dest
    print(f"Scaffolded {rel}")
    print(f"  package:  {pkg}")
    print(f"  project:  {kebab}")
    print(f"  command:  {command}")
    print("\nNext steps:")
    print(f"  1. cd {rel} && uv sync")
    if kind == "package":
        print(f"  2. uv run {command} eval        # DRY_RUN smoke test (no creds needed)")
        print("  3. Fill the TODO stubs: app.py (real logic), prompts.py, data/cases.json, README.md")
        print("  4. uv run ruff check . && bash run.sh   # what CI runs (dry-run without creds)")
    else:
        print(f"  2. uv run {command} --dry-run   # DRY_RUN smoke test (no creds needed)")
        print(f"  3. Fill the TODO in {pkg}.py (real logic) and the README.md sections")
        print("  4. uv run ruff check . && bash run.sh   # what CI runs (dry-run without creds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
