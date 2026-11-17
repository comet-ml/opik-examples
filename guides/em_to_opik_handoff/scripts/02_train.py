"""Fine-tune YOLO on the prepared dataset, tracked in Comet Experiment Management.

Usage: uv run python scripts/02_train.py [--epochs 30] [--imgsz 640] [--name baseline]
Run scripts/01_prepare_data.py first: it logs the dataset Artifact this run declares as its input.

Notes on the Ultralytics Comet callback (ultralytics 8.4.x, utils/callbacks/comet.py):
- It calls comet_ml.start(project_name=COMET_PROJECT_NAME or args.project), which reuses an
  experiment already running in this process. So this script starts the experiment first,
  declares the dataset Artifact as its input, then trains.
- Env vars it honours: COMET_PROJECT_NAME, COMET_MODEL_NAME (name best.pt is logged under),
  COMET_EVAL_LOG_IMAGE_PREDICTIONS, COMET_MAX_IMAGE_PREDICTIONS,
  COMET_EVAL_BATCH_LOGGING_INTERVAL, COMET_MAX_CONFIDENCE_SCORE, COMET_START_ONLINE.
- The final confusion matrix is always logged. COMET_EVAL_LOG_CONFUSION_MATRIX only adds one
  per checkpoint, and only when Ultralytics save_period is set.
- It logs best.pt as a model at train end and ends the experiment on teardown, before train()
  returns. Anything this script logs on the experiment is logged before training starts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from roadwork_demo.config import REPO_ROOT, Settings, get_settings
from roadwork_demo.registry import labels_fingerprint, latest_artifact


def prepared_artifact_version(s: Settings, yolo_dir: Path) -> str:
    """Version of the dataset Artifact that holds the local labels. Exits if there is none."""
    hint = "Run scripts/01_prepare_data.py first."
    latest = latest_artifact(s.workspace, s.dataset_artifact)
    if latest is None:
        sys.exit(f"Dataset artifact '{s.dataset_artifact}' not found in workspace '{s.workspace}'. {hint}")
    version, fingerprint = latest
    if fingerprint != labels_fingerprint(yolo_dir):
        # WHY: the lineage must name the labels this run really trains on.
        sys.exit(f"The local labels differ from {s.dataset_artifact}:{version}. {hint}")
    return version


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--model", default="yolo11s.pt")
    ap.add_argument("--name", default="baseline")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--fraction", type=float, default=1.0, help="fraction of train set to use")
    args = ap.parse_args()

    s = get_settings()
    os.environ["COMET_PROJECT_NAME"] = s.project
    os.environ["COMET_MODEL_NAME"] = s.registry_model
    os.environ.setdefault("COMET_MAX_IMAGE_PREDICTIONS", "100")
    os.environ.setdefault("COMET_EVAL_BATCH_LOGGING_INTERVAL", "4")

    import comet_ml
    from ultralytics import YOLO

    yolo_dir = s.data_dir / "yolo"
    artifact_version = prepared_artifact_version(s, yolo_dir)
    experiment = comet_ml.start(workspace=s.workspace or None, project_name=s.project)
    experiment.set_name(f"{Path(args.model).stem}-{args.name}")
    experiment.add_tags(["roadwork", Path(args.model).stem, args.name])
    experiment_key = experiment.get_key()
    # WHY: get_artifact on the experiment is what records this run as a consumer in the lineage.
    logged = experiment.get_artifact(
        s.dataset_artifact, workspace=s.workspace or None, version_or_alias=artifact_version
    )
    dataset_artifact = f"{s.dataset_artifact}:{logged.version}"
    experiment.log_other("dataset_artifact", dataset_artifact)
    print(f"Training on dataset artifact {dataset_artifact}")

    model = YOLO(args.model)
    results = model.train(
        data=str(yolo_dir / "data.yaml"),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(REPO_ROOT / "runs" / s.project),
        name=args.name,
        exist_ok=True,
        save_json=True,
        fraction=args.fraction,
        workers=8,
    )

    metrics = results.results_dict
    out = {
        "experiment_key": experiment_key,
        "best_weights": str(model.trainer.best),
        "map50": float(metrics.get("metrics/mAP50(B)", 0.0)),
        "map50_95": float(metrics.get("metrics/mAP50-95(B)", 0.0)),
        "dataset_artifact": dataset_artifact,
        "classes": [model.names[i] for i in sorted(model.names)],
        "name": args.name,
    }
    runs = REPO_ROOT / "runs"
    runs.mkdir(exist_ok=True)
    (runs / "last_experiment.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
