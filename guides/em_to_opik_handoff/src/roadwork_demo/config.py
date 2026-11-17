"""Settings from the environment and the EM -> Opik handoff contract."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    comet_workspace: str
    comet_project: str
    registry_model: str
    dataset_artifact: str
    opik_project: str
    opik_dataset: str
    prompt_name: str
    queue_name: str
    verdict_model: str
    judge_model: str
    online_judge_model: str
    anthropic_api_key: str
    anthropic_api_url: str
    data_dir: Path
    handoff_path: Path

    @property
    def eval_manifest_path(self) -> Path:
        return self.data_dir / "eval_manifest.json"

    @property
    def dev_dataset(self) -> str:
        """Small subset dataset for quick iteration (scripts/04 --limit)."""
        return f"{self.opik_dataset}-dev"


def get_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    env = os.environ.get
    # WHY: Opik falls back to a default project from user config for traces created outside
    # our @track decorators (for example by evaluate()). Pin it to this demo's project.
    opik_project = env("OPIK_PROJECT") or "roadwork-triage"
    os.environ["OPIK_PROJECT_NAME"] = opik_project
    judge_model = env("JUDGE_MODEL") or "claude-sonnet-5-5"
    return Settings(
        comet_workspace=env("COMET_WORKSPACE_NAME") or env("COMET_WORKSPACE") or "",
        comet_project=env("COMET_PROJECT") or "roadwork-detector",
        registry_model=env("REGISTRY_MODEL") or "roadwork-yolo11s",
        dataset_artifact=env("DATASET_ARTIFACT") or "roadwork-yolo",
        opik_project=opik_project,
        opik_dataset=env("OPIK_DATASET") or "roadwork-verdicts-v1",
        prompt_name=env("PROMPT_NAME") or "roadwork-verdict",
        queue_name=env("QUEUE_NAME") or "roadwork-review",
        verdict_model=env("VERDICT_MODEL") or "claude-haiku-5-5",
        judge_model=judge_model,
        online_judge_model=env("ONLINE_JUDGE_MODEL") or judge_model,
        anthropic_api_key=env("ANTHROPIC_API_KEY") or "",
        # WHY: never fall back to ANTHROPIC_BASE_URL; a shell may point it at a proxy.
        anthropic_api_url=env("ANTHROPIC_API_URL") or "https://api.anthropic.com",
        data_dir=Path(env("DATA_DIR") or REPO_ROOT / "data"),
        handoff_path=Path(env("HANDOFF_PATH") or REPO_ROOT / "handoff.json"),
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
            f"{path} is missing field(s): {', '.join(missing)}. "
            "Re-run scripts/03_register.py."
        )
    return Handoff(**{f.name: data[f.name] for f in fields(Handoff)})


DEV_VERSION = "dev-stock"
VARIANTS = ("vlm_only", "detector_vlm")


def is_full_run(dataset_name: str, default_dataset: str, nb_samples: int | None) -> bool:
    """True for a run over every item of the default verdict dataset."""
    return dataset_name == default_dataset and nb_samples is None


def experiment_name(variant: str, model_version: str, full_run: bool = True) -> str:
    """Opik experiment name. Subset and dev-dataset runs get a "-dev" suffix so they never
    share a name with the full run that the gate and the Comet back-link read."""
    return f"{variant}-{model_version}" + ("" if full_run else "-dev")


def variant_tag(variant: str) -> str:
    return f"variant:{variant}"


def should_link_back(
    model_version: str, dataset_name: str, default_dataset: str, nb_samples: int | None
) -> bool:
    """Write Opik results onto the Comet experiment only for a full run on a registered model.

    Subset or dev-dataset runs would overwrite the headline numbers with partial ones.
    """
    return model_version != DEV_VERSION and is_full_run(dataset_name, default_dataset, nb_samples)
