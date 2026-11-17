"""Convert ROADWork to YOLO format and build the verdict eval manifest.

Usage: uv run python scripts/01_prepare_data.py [--max-train N]
Expects data/raw/roadwork/images.zip and data/raw/roadwork/annotations/ (see README).
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

from roadwork_demo.config import get_settings
from roadwork_demo.data import (
    build_image_index,
    convert_split,
    find_image,
    select_eval_frames,
    verdict_from_tags,
    write_data_yaml,
)

IMAGES_URL = "https://ndownloader.figshare.com/files/47217577"
MIN_ZIP_BYTES = 10_000_000_000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-train", type=int, default=None, help="subsample training images")
    args = ap.parse_args()

    s = get_settings()
    raw = s.data_dir / "raw" / "roadwork"
    ann_dir = raw / "annotations"
    img_root = raw / "images"
    zip_path = raw / "images.zip"

    if not img_root.exists():
        if not zip_path.exists() or zip_path.stat().st_size < MIN_ZIP_BYTES:
            sys.exit(
                f"{zip_path} missing or incomplete. Resume with:\n"
                f"  curl -L -C - -o {zip_path} {IMAGES_URL}"
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
    for i, name in enumerate(classes, start=1):
        print(f"  {name:45s} {hist.get(i, 0)}")

    val_images = [im for im in val_coco["images"] if find_image(image_index, im["file_name"])]
    print(
        "Val verdicts from raw tags (before the description filter on blocked):",
        dict(Counter(verdict_from_tags(im["scene_level_tags"].get("travel_alteration")) for im in val_images)),
    )
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


if __name__ == "__main__":
    main()
