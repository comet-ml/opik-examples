"""Fine-tune YOLO on the prepared dataset, tracked in Comet Experiment Management.

Usage: uv run python scripts/02_train.py [--epochs 30] [--name baseline]

Notes on the Ultralytics Comet callback (ultralytics 8.4.x, utils/callbacks/comet.py):
- It calls comet_ml.start(project_name=COMET_PROJECT_NAME or args.project), which reuses an
  experiment already running in this process. So we start the experiment first, log the
  dataset Artifact on it, then train.
- Env vars it honours: COMET_PROJECT_NAME, COMET_MODEL_NAME (name best.pt is logged under),
  COMET_EVAL_LOG_CONFUSION_MATRIX, COMET_EVAL_LOG_IMAGE_PREDICTIONS,
  COMET_MAX_IMAGE_PREDICTIONS, COMET_EVAL_BATCH_LOGGING_INTERVAL, COMET_START_ONLINE.
- It logs best.pt as a model at train end and ends the experiment on teardown.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from roadwork_demo.config import REPO_ROOT, get_settings
from roadwork_demo.registry import fingerprint_dir

SOURCE_URL = "https://kilthub.cmu.edu/articles/dataset/ROADWork_Data/26093197"


def get_or_log_dataset_artifact(experiment, s, yolo_dir: Path) -> str:
    """Attach the training dataset Artifact to the experiment. Returns 'name:version'.

    The artifact is reused only if its labels are byte-identical to the local ones
    (fingerprint in the artifact metadata); otherwise a new version is logged.
    """
    import comet_ml
    from comet_ml.exceptions import ArtifactNotFound

    fingerprint = fingerprint_dir(yolo_dir / "labels")
    try:
        logged = experiment.get_artifact(s.dataset_artifact)
    except ArtifactNotFound:
        logged = None
    if logged is not None and (logged.metadata or {}).get("fingerprint") == fingerprint:
        print(f"Using existing dataset artifact {s.dataset_artifact}:{logged.version}")
        return f"{s.dataset_artifact}:{logged.version}"

    n_train = len(list((yolo_dir / "images" / "train").iterdir()))
    n_val = len(list((yolo_dir / "images" / "val").iterdir()))
    artifact = comet_ml.Artifact(
        name=s.dataset_artifact,
        artifact_type="dataset",
        # First version is 1.0.0; later versions are numbered by Comet.
        version="1.0.0" if logged is None else None,
        aliases=["baseline"] if logged is None else None,
        metadata={
            "source": "CMU ROADWork",
            "source_url": SOURCE_URL,
            "license": "ODC-By 1.0 (images not redistributed in this artifact)",
            "train_images": n_train,
            "val_images": n_val,
            "format": "YOLO labels + data.yaml",
            "fingerprint": fingerprint,
        },
    )
    # WHY: labels and class list only. Images stay local; the artifact pins which files and
    # labels were used for training without redistributing the dataset.
    labels_zip = shutil.make_archive(str(s.data_dir / "labels"), "zip", yolo_dir / "labels")
    artifact.add(labels_zip, logical_path="labels.zip")
    artifact.add(str(yolo_dir / "data.yaml"), logical_path="data.yaml")
    logged = experiment.log_artifact(artifact)
    print(f"Logged dataset artifact {s.dataset_artifact}:{logged.version}")
    return f"{s.dataset_artifact}:{logged.version}"


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
    os.environ["COMET_PROJECT_NAME"] = s.comet_project
    os.environ["COMET_MODEL_NAME"] = s.registry_model
    os.environ.setdefault("COMET_EVAL_LOG_CONFUSION_MATRIX", "true")
    os.environ.setdefault("COMET_MAX_IMAGE_PREDICTIONS", "100")
    os.environ.setdefault("COMET_EVAL_BATCH_LOGGING_INTERVAL", "4")

    import comet_ml
    from ultralytics import YOLO

    yolo_dir = s.data_dir / "yolo"
    experiment = comet_ml.start(workspace=s.comet_workspace or None, project_name=s.comet_project)
    experiment.set_name(f"{Path(args.model).stem}-{args.name}")
    experiment.add_tags(["roadwork", Path(args.model).stem, args.name])
    experiment_key = experiment.get_key()
    dataset_artifact = get_or_log_dataset_artifact(experiment, s, yolo_dir)
    experiment.log_other("dataset_artifact", dataset_artifact)

    model = YOLO(args.model)
    results = model.train(
        data=str(yolo_dir / "data.yaml"),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(REPO_ROOT / "runs" / s.comet_project),
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
