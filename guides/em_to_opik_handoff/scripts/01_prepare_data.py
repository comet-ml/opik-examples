"""Convert ROADWork to YOLO format, build the verdict eval manifest, log the dataset Artifact.

Usage: uv run python scripts/01_prepare_data.py [--max-train N] [--no-comet]
Expects data/raw/roadwork/images.zip and data/raw/roadwork/annotations/ (see README).

The labels and class list are logged as a Comet Artifact from a short "prepare-data" experiment,
so the lineage shows data preparation as the producer and every training run as a consumer.
Safe to re-run: unchanged labels reuse the existing Artifact version and start no experiment.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

from roadwork_demo.config import Settings, comet_ready, get_settings
from roadwork_demo.data import (
    build_image_index,
    convert_split,
    find_image,
    portable_data_yaml,
    select_eval_frames,
    write_data_yaml,
)
from roadwork_demo.registry import labels_fingerprint, latest_artifact

IMAGES_URL = "https://ndownloader.figshare.com/files/47217577"
SOURCE_URL = "https://kilthub.cmu.edu/articles/dataset/ROADWork_Data/26093197"
MIN_ZIP_BYTES = 10_000_000_000


def get_or_log_dataset_artifact(s: Settings, yolo_dir: Path) -> str:
    """Log the YOLO labels as a dataset Artifact and return its 'name:version'."""
    # WHY: the newest version is reused when its labels are byte-identical to the local ones
    # (fingerprint in the artifact metadata); then no "prepare-data" experiment is started.
    import comet_ml

    fingerprint = labels_fingerprint(yolo_dir)
    latest = latest_artifact(s.workspace, s.dataset_artifact)
    if latest is not None and latest[1] == fingerprint:
        print(f"Using existing dataset artifact {s.dataset_artifact}:{latest[0]} (labels unchanged)")
        return f"{s.dataset_artifact}:{latest[0]}"

    n_train = len(list((yolo_dir / "images" / "train").iterdir()))
    n_val = len(list((yolo_dir / "images" / "val").iterdir()))
    artifact = comet_ml.Artifact(
        name=s.dataset_artifact,
        artifact_type="dataset",
        # First version is 1.0.0; later versions are numbered by Comet.
        version="1.0.0" if latest is None else None,
        aliases=["baseline"] if latest is None else None,
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
    # labels were used for training without redistributing the dataset. The remote entry is a
    # provenance pointer to where the images come from, not a copy.
    labels_dir = yolo_dir / "labels"
    labels_zip = s.data_dir / "labels.zip"
    with zipfile.ZipFile(labels_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(labels_dir.rglob("*.txt")):
            z.write(path, path.relative_to(labels_dir))
    artifact.add(str(labels_zip), logical_path="labels.zip")
    # WHY: the local data.yaml starts with this machine's absolute dataset path.
    shared_yaml = s.data_dir / "data.portable.yaml"
    shared_yaml.write_text(portable_data_yaml((yolo_dir / "data.yaml").read_text()))
    artifact.add(str(shared_yaml), logical_path="data.yaml")
    artifact.add_remote(SOURCE_URL, logical_path="images")

    experiment = comet_ml.start(workspace=s.workspace or None, project_name=s.project)
    experiment.set_name("prepare-data")
    experiment.add_tags(["roadwork", "prepare-data"])
    logged = experiment.log_artifact(artifact)
    experiment.end()
    print(f"Logged dataset artifact {s.dataset_artifact}:{logged.version} from experiment prepare-data")
    return f"{s.dataset_artifact}:{logged.version}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-train", type=int, default=None, help="subsample training images")
    ap.add_argument("--no-comet", action="store_true", help="prepare the data only, log no Artifact")
    args = ap.parse_args()

    s = get_settings()
    raw = s.data_dir / "raw" / "roadwork"
    ann_dir = raw / "annotations"
    img_root = raw / "images"
    zip_path = raw / "images.zip"

    if not img_root.exists():
        if not zip_path.exists() or zip_path.stat().st_size < MIN_ZIP_BYTES:
            sys.exit(
                f"{zip_path} missing or incomplete. Resume with:\n  curl -L -C - -o {zip_path} {IMAGES_URL}"
            )
        print("Unzipping images (about 10 GB)...")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(raw)

    image_index = build_image_index(img_root)
    print(f"Images on disk: {len(image_index)}")

    out = s.data_dir / "yolo"
    train_json = ann_dir / "instances_train_gps_split.json"
    val_json = ann_dir / "instances_val_gps_split.json"
    train_coco = json.loads(train_json.read_text())
    val_coco = json.loads(val_json.read_text())
    classes = [c["name"] for c in sorted(train_coco["categories"], key=lambda c: c["id"])]

    for name, coco in (("train", train_coco), ("val", val_coco)):
        missing = [im["file_name"] for im in coco["images"] if not find_image(image_index, im["file_name"])]
        print(f"{name}: {len(coco['images'])} annotated, {len(missing)} not found on disk")

    n_train = convert_split(train_json, image_index, out, "train", max_images=args.max_train)
    n_val = convert_split(val_json, image_index, out, "val")
    yaml_path = write_data_yaml(out, classes)
    print(f"YOLO dataset: train {n_train}, val {n_val} -> {yaml_path}")

    hist = Counter(a["category_id"] for a in train_coco["annotations"])
    print("Train class histogram:")
    for category in sorted(train_coco["categories"], key=lambda c: c["id"]):
        print(f"  {category['name']:45s} {hist.get(category['id'], 0)}")

    val_images = [im for im in val_coco["images"] if find_image(image_index, im["file_name"])]
    manifest = select_eval_frames(val_images, per_class=50, seed=7)
    for item in manifest:
        item["path"] = str(find_image(image_index, item["file_name"]))
    manifest_path = s.eval_manifest_path
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Eval manifest: {dict(Counter(i['verdict'] for i in manifest))} -> {manifest_path}")

    # Debug overlays: draw YOLO labels back onto 20 random training frames.
    dbg = s.data_dir / "debug_overlays"
    dbg.mkdir(exist_ok=True)
    label_files = sorted((out / "labels" / "train").glob("*.txt"))
    for lbl in random.Random(7).sample(label_files, min(20, len(label_files))):
        img = Image.open(next((out / "images" / "train").glob(lbl.stem + ".*"))).convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        for line in lbl.read_text().splitlines():
            c, cx, cy, bw, bh = line.split()
            cx, cy, bw, bh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
            draw.rectangle([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], outline="red", width=4)
            draw.text((cx - bw / 2, cy - bh / 2 - 12), classes[int(c)], fill="red")
        img.thumbnail((1280, 1280))
        img.save(dbg / (lbl.stem + ".jpg"))
    print(f"Debug overlays -> {dbg}")

    if args.no_comet:
        print("Skipping the dataset Artifact (--no-comet).")
    elif not comet_ready(s):
        print(
            f"[DRY RUN] COMET_API_KEY or COMET_WORKSPACE not set: would log the labels as Artifact "
            f"'{s.dataset_artifact}' (fingerprint {labels_fingerprint(out)}) "
            "from a prepare-data experiment."
        )
    else:
        get_or_log_dataset_artifact(s, out)


if __name__ == "__main__":
    main()
