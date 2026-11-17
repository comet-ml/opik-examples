"""Model Registry helpers: version numbers, statuses, and the registry-resolved handoff."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from roadwork_demo.config import STOCK_VERSION, Handoff, HandoffError

PRODUCTION = "production"
STATUS_PRODUCTION = "Production"
STATUS_STAGING = "Staging"
STOCK_MODEL = "yolo11s"
MAP50 = "metrics/mAP50(B)"
MAP50_95 = "metrics/mAP50-95(B)"


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


def fingerprint_dir(root: Path, pattern: str = "*") -> str:
    """Content hash of the files under `root` matching `pattern` (relative path + bytes)."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob(pattern) if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def labels_fingerprint(yolo_dir: Path) -> str:
    """Fingerprint of the YOLO label files, the identity of a dataset Artifact version."""
    # WHY: label .txt files only. Ultralytics writes train.cache and val.cache into the same
    # folder on every training run; hashing them would make every run look like new data.
    return fingerprint_dir(Path(yolo_dir) / "labels", "*.txt")


def latest_artifact(workspace: str, name: str, api: Any = None) -> tuple[str, str | None] | None:
    """(version, labels fingerprint) of the newest version of a dataset Artifact, None if not logged."""
    if api is None:
        from comet_ml import API

        api = API()
    # WHY: asking for an artifact name that was never logged fails with a generic HTTP 400, not
    # with ArtifactNotFound, so existence is read from the workspace's artifact list instead.
    listed = api.get_artifact_list(workspace).get("artifacts") or []
    if name not in {a["name"] for a in listed}:
        return None
    artifact = api.get_artifact(workspace, name)
    return str(artifact.version), (artifact.metadata or {}).get("fingerprint")


def pick_version(detector: str, versions: list[str], production: list[str]) -> str:
    """Registry version for a --detector value: "production" or an explicit version."""
    known = ", ".join(versions) or "none"
    if detector == PRODUCTION:
        if not production:
            # WHY: no fallback to the newest version; that would serve a candidate the gate held.
            raise HandoffError(
                f"No registry version has status {STATUS_PRODUCTION} (registered versions: {known}). "
                "Promote one with `python -m roadwork_demo.gate --candidate <version> --apply`, set the "
                "status in the Comet Model Registry, or name a version with --detector <version> "
                "(env DETECTOR_VERSION)."
            )
        return production[0]
    if detector not in versions:
        raise HandoffError(f"Version '{detector}' is not in the registry. Registered versions: {known}.")
    return detector


def initial_status(production: list[str]) -> str:
    """The first registered model is what is deployed; every later one has to pass the gate."""
    return STATUS_STAGING if production else STATUS_PRODUCTION


def stock_handoff(workspace: str, project: str) -> Handoff:
    """Identity of the COCO-pretrained baseline: no training run, no registry entry."""
    return Handoff(
        comet_workspace=workspace,
        comet_project=project,
        experiment_key="",
        experiment_url="",
        registry_model=STOCK_MODEL,
        model_version=STOCK_VERSION,
        dataset_artifact="none",
        classes=[],
        map50=0.0,
        map50_95=0.0,
    )


def _metric(experiment: Any, name: str) -> float:
    summary = experiment.get_metrics_summary(name)
    return float(summary["valueCurrent"]) if summary else 0.0


def resolve_handoff(
    workspace: str, registry_model: str, detector: str, project: str, api: Any = None
) -> Handoff:
    """Everything the Opik side knows about the training side, read from `workspace/model:version`."""
    if detector == STOCK_VERSION:
        return stock_handoff(workspace, project)
    try:
        if api is None:
            from comet_ml import API

            api = API()
        model = api.get_model(workspace, registry_model)
    except Exception as exc:
        raise HandoffError(
            f"Could not read registry model '{workspace}/{registry_model}': {exc}. Train and register "
            "one first (scripts/02_train.py, then scripts/03_register.py), or use --detector stock."
        ) from exc
    version = pick_version(detector, model.find_versions(), model.find_versions(status=STATUS_PRODUCTION))
    key = model.get_details(version).get("experimentKey")
    experiment = api.get_experiment_by_key(key) if key else None
    if experiment is None:
        raise HandoffError(
            f"{registry_model}:{version} was registered from Comet experiment '{key}', which no longer "
            "exists. Pick another version with --detector, or register the model again."
        )
    artifact = experiment.get_others_summary("dataset_artifact")
    return Handoff(
        comet_workspace=workspace,
        comet_project=project,
        experiment_key=key,
        experiment_url=experiment.url,
        registry_model=registry_model,
        model_version=version,
        dataset_artifact=artifact[0] if artifact else "unknown",
        classes=[],
        map50=_metric(experiment, MAP50),
        map50_95=_metric(experiment, MAP50_95),
    )
