"""Register the trained model in the Comet Model Registry and write handoff.json.

Usage: uv run python scripts/03_register.py [--name baseline]
Reads runs/last_experiment.json written by scripts/02_train.py.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from comet_ml import API

from roadwork_demo.config import REPO_ROOT, Handoff, get_settings, save_handoff
from roadwork_demo.data import load_eval_manifest
from roadwork_demo.pipeline import load_detector, registry_cache_dir
from roadwork_demo.registry import next_version, registered_version


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="baseline", help="name of the training run to register")
    args = ap.parse_args()

    s = get_settings()
    last_path = REPO_ROOT / "runs" / "last_experiment.json"
    if not last_path.exists():
        sys.exit("runs/last_experiment.json not found. Run scripts/02_train.py first.")
    last = json.loads(last_path.read_text())
    # WHY: every training run overwrites last_experiment.json, also a 1-epoch smoke run.
    if last.get("name") != args.name:
        sys.exit(
            f"The last training run is named '{last.get('name')}', not '{args.name}'. "
            f"Pass --name {last.get('name')} to register it anyway, or re-run scripts/02_train.py."
        )

    api = API()
    exp = api.get_experiment_by_key(last["experiment_key"])
    workspace = s.workspace or exp.workspace

    print(
        f"Experiment {last['experiment_key']} (run '{last.get('name')}'): "
        f"mAP50={last['map50']:.3f}, mAP50-95={last['map50_95']:.3f}"
    )

    others = {o["name"]: o.get("valueCurrent") for o in exp.get_others_summary()}
    version = registered_version(others.get("registry_model"), s.registry_model)
    if version:
        # Safe to re-run: this experiment's model is already in the registry.
        print(f"Already registered as {s.registry_model}:{version}; not registering again.")
    else:
        if s.registry_model not in exp.get_model_names():
            sys.exit(
                f"The experiment has no logged model named '{s.registry_model}' "
                f"(found: {exp.get_model_names()}). REGISTRY_MODEL must be the same for "
                "scripts/02_train.py and scripts/03_register.py; re-run training or fix .env."
            )
        try:
            existing = api.get_registry_model_versions(workspace, s.registry_model) or []
        except Exception:
            existing = []  # model not in the registry yet
        version = next_version(existing)
        exp.register_model(
            model_name=s.registry_model,
            version=version,
            workspace=workspace,
            registry_name=s.registry_model,
            description="YOLO11 work-zone object detector fine-tuned on CMU ROADWork.",
            comment=f"mAP50={last['map50']:.3f} mAP50-95={last['map50_95']:.3f} "
            f"dataset={last['dataset_artifact']}",
            tags=[last.get("name", "baseline")],
        )
        exp.log_other("registry_model", f"{s.registry_model}:{version}")
        print(f"Registered {workspace}/{s.registry_model}:{version}")

    handoff = Handoff(
        comet_workspace=workspace,
        comet_project=s.project,
        experiment_key=last["experiment_key"],
        experiment_url=exp.url,
        registry_model=s.registry_model,
        model_version=version,
        dataset_artifact=last["dataset_artifact"],
        classes=last["classes"],
        map50=last["map50"],
        map50_95=last["map50_95"],
    )
    save_handoff(handoff, s.handoff_path)
    print(f"Registry: https://www.comet.com/{workspace}/model-registry/{s.registry_model}")
    print(f"Wrote {s.handoff_path}")

    # Verify: what the registry serves loads and predicts. Uses the pipeline's own loader, so
    # the download also fills the cache the Opik scripts read from. The cache is cleared first:
    # the check must exercise a real download, and a version number may have been reused.
    shutil.rmtree(registry_cache_dir(s.registry_model, version), ignore_errors=True)
    frame = load_eval_manifest(s.eval_manifest_path)[0]["path"]
    result = load_detector(handoff).predict(frame, verbose=False)[0]
    labels = [result.names[int(c)] for c in result.boxes.cls]
    print(f"Verification: registry weights predicted {len(labels)} objects: {sorted(set(labels))}")


if __name__ == "__main__":
    main()
