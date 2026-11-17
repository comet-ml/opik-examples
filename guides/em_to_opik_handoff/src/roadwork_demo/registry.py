"""Model Registry helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def next_version(existing: list[str]) -> str:
    """1.0.0 for a new model, else bump the major of the highest version.

    Versions are compared as integer tuples so "10.0.0" sorts after "9.0.0".
    """
    parsed = []
    for v in existing:
        try:
            parsed.append(tuple(int(p) for p in str(v).split(".")))
        except ValueError:
            continue
    if not parsed:
        return "1.0.0"
    return f"{max(parsed)[0] + 1}.0.0"


def registered_version(registry_other: str | None, registry_model: str) -> str | None:
    """Version already registered from an experiment, read from its 'registry_model' field.

    The field is written as "<model>:<version>" by scripts/03_register.py.
    """
    if not registry_other or ":" not in registry_other:
        return None
    name, version = registry_other.rsplit(":", 1)
    return version if name == registry_model and version else None


def fingerprint_dir(root: Path) -> str:
    """Content hash of every file under `root` (relative path + bytes), order independent."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]
