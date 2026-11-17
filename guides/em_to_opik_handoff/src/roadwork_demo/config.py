"""Settings from the environment and the EM -> Opik handoff contract."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

STOCK_VERSION = "stock"
DEV_VERSION = "dev-stock"
VARIANTS = ("vlm_only", "detector_vlm")


@dataclass(frozen=True)
class Settings:
    workspace: str
    project: str
    registry_model: str
    dataset_artifact: str
    opik_dataset: str
    prompt_name: str
    queue_name: str
    verdict_model: str
    judge_model: str
    online_judge_model: str
    detector: str
    data_dir: Path
    handoff_path: Path
    dry_run: bool

    @property
    def eval_manifest_path(self) -> Path:
        return self.data_dir / "eval_manifest.json"

    @property
    def dev_dataset(self) -> str:
        """Small subset dataset for quick iteration (scripts/04 --limit)."""
        return f"{self.opik_dataset}-dev"


def get_settings() -> Settings:
    # WHY: every lookup falls back with `or`, not a .get default: an unset CI variable arrives as "".
    env = os.environ.get
    # WHY: Opik falls back to a default project from user config for traces created outside
    # our @track decorators (for example by evaluate()). Pin it to this guide's project.
    project = env("OPIK_PROJECT_NAME") or "roadwork-detection"
    os.environ["OPIK_PROJECT_NAME"] = project
    return Settings(
        workspace=env("COMET_WORKSPACE") or env("OPIK_WORKSPACE") or "",
        project=project,
        registry_model=env("REGISTRY_MODEL") or "roadwork-yolo11s",
        dataset_artifact=env("DATASET_ARTIFACT") or "roadwork-yolo",
        opik_dataset=env("OPIK_DATASET") or "roadwork-verdicts",
        prompt_name=env("PROMPT_NAME") or "roadwork-verdict",
        queue_name=env("QUEUE_NAME") or "roadwork-review",
        verdict_model=env("OPIK_EXAMPLES_MODEL") or "anthropic/claude-haiku-5-5",
        judge_model=env("JUDGE_MODEL") or "anthropic/claude-sonnet-5-5",
        online_judge_model=env("OPIK_ONLINE_JUDGE_MODEL") or "opik-free-model",
        detector=env("DETECTOR_VERSION") or "production",
        data_dir=Path(env("DATA_DIR") or REPO_ROOT / "data"),
        handoff_path=Path(env("HANDOFF_PATH") or REPO_ROOT / "handoff.json"),
        dry_run=not (env("OPIK_API_KEY") and env("OPIK_WORKSPACE")),
    )


class HandoffError(RuntimeError):
    pass


@dataclass
class Handoff:
    """Everything the Opik side knows about the training side."""

    comet_workspace: str
    comet_project: str
    experiment_key: str
    experiment_url: str
    registry_model: str
    model_version: str
    dataset_artifact: str
    classes: list[str]
    map50: float
    map50_95: float

    def model_tag(self) -> str:
        return f"detector:{self.registry_model}:{self.model_version}"

    def as_metadata(self) -> dict:
        md = asdict(self)
        md.pop("classes")
        md["em_url"] = self.experiment_url
        return md


def save_handoff(h: Handoff, path: Path) -> None:
    Path(path).write_text(json.dumps(asdict(h), indent=2) + "\n")


def load_handoff(path: Path) -> Handoff:
    path = Path(path)
    if not path.exists():
        raise HandoffError(
            f"{path} not found. Train and register a model first: "
            "run scripts/02_train.py then scripts/03_register.py."
        )
    data = json.loads(path.read_text())
    missing = [f.name for f in fields(Handoff) if f.name not in data]
    if missing:
        raise HandoffError(
            f"{path} is missing field(s): {', '.join(missing)}. Re-run scripts/03_register.py."
        )
    return Handoff(**{f.name: data[f.name] for f in fields(Handoff)})


def is_full_run(dataset_name: str, default_dataset: str, nb_samples: int | None) -> bool:
    """True for a run over every item of the default verdict dataset."""
    return dataset_name == default_dataset and nb_samples is None


def experiment_name(variant: str, model_version: str | None, full_run: bool = True) -> str:
    """Opik experiment name. Subset and dev-dataset runs get a "-dev" suffix so they never
    share a name with the full run that the gate and the Comet back-link read."""
    # WHY: vlm_only runs no detector, so one experiment serves every detector version.
    base = variant if variant == "vlm_only" or model_version is None else f"{variant}-{model_version}"
    return base + ("" if full_run else "-dev")


def variant_tag(variant: str) -> str:
    return f"variant:{variant}"


def should_link_back(
    model_version: str, dataset_name: str, default_dataset: str, nb_samples: int | None
) -> bool:
    """Write Opik results onto the Comet experiment only for a full run on a registered model.

    Subset or dev-dataset runs would overwrite the headline numbers with partial ones.
    """
    registered = model_version not in (STOCK_VERSION, DEV_VERSION)
    return registered and is_full_run(dataset_name, default_dataset, nb_samples)
