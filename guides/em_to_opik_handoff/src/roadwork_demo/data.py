"""ROADWork (COCO-style) -> YOLO conversion and verdict ground truth."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path

VERDICTS = ("blocked", "partial", "clear")


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def build_image_index(root: Path) -> dict[str, Path]:
    """Map lower-cased file name -> path. ROADWork mixes .jpg and .JPG."""
    return {
        p.name.lower(): p
        for p in Path(root).rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    }


def find_image(image_index: dict[str, Path], file_name: str) -> Path | None:
    return image_index.get(file_name.lower())


def verdict_from_tags(tags: list[str] | None) -> str | None:
    """Map ROADWork `travel_alteration` tags to a verdict; None means "exclude"."""
    tags = list(tags or [])
    if "Fully Blocked" in tags:
        return "blocked"
    if "Partially Blocked" in tags or "Lane Shift" in tags:
        return "partial"
    if tags == ["None"]:
        return "clear"
    return None


def coco_bbox_to_yolo(
    bbox: list[float], img_w: int, img_h: int
) -> tuple[float, float, float, float] | None:
    x, y, w, h = bbox
    x1, y1 = max(0.0, x), max(0.0, y)
    x2, y2 = min(float(img_w), x + w), min(float(img_h), y + h)
    if x2 <= x1 or y2 <= y1:
        return None
    return (
        (x1 + x2) / 2 / img_w,
        (y1 + y2) / 2 / img_h,
        (x2 - x1) / img_w,
        (y2 - y1) / img_h,
    )


def convert_split(
    coco_json: Path,
    image_index: dict[str, Path],
    out_dir: Path,
    split: str,
    max_images: int | None = None,
    seed: int = 7,
) -> int:
    """Write YOLO labels and image symlinks for one split. Returns images written."""
    coco = json.loads(Path(coco_json).read_text())
    images = [im for im in coco["images"] if find_image(image_index, im["file_name"])]
    if max_images is not None and len(images) > max_images:
        images = random.Random(seed).sample(
            sorted(images, key=lambda im: im["file_name"]), max_images
        )
    # WHY: YOLO class index = position in data.yaml (categories sorted by id). COCO ids need
    # not start at 1 or be contiguous.
    class_index = {
        c["id"]: i for i, c in enumerate(sorted(coco["categories"], key=lambda c: c["id"]))
    }
    anns = defaultdict(list)
    for a in coco["annotations"]:
        anns[a["image_id"]].append(a)

    img_dir = Path(out_dir) / "images" / split
    lbl_dir = Path(out_dir) / "labels" / split
    # WHY: start from empty folders so a smaller rerun (--max-train) does not keep old files.
    for folder in (img_dir, lbl_dir):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)

    for im in images:
        name = im["file_name"]
        lines = []
        for a in anns[im["id"]]:
            box = coco_bbox_to_yolo(a["bbox"], im["width"], im["height"])
            if box is not None:
                lines.append(f"{class_index[a['category_id']]} " + " ".join(f"{v:.6f}" for v in box))
        (lbl_dir / (Path(name).stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
        os.symlink(Path(find_image(image_index, name)).resolve(), img_dir / name)
    return len(images)


def write_data_yaml(out_dir: Path, classes: list[str]) -> Path:
    out_dir = Path(out_dir)
    lines = [f"path: {out_dir.resolve()}", "train: images/train", "val: images/val", "names:"]
    lines += [f"  {i}: {name}" for i, name in enumerate(classes)]
    path = out_dir / "data.yaml"
    path.write_text("\n".join(lines) + "\n")
    return path


_CLOSED = re.compile(r"fully block|road closed|road is closed")
_NOT_OWN_ROAD = re.compile(
    r"intersecting|sidewalk|side road|side street|crosswalk|bike lane|\blanes?\b|parking|"
    r"driveway|shoulder|ramp|alley"
)


def describes_own_road_closed(description: str) -> bool:
    """True if a sentence of the human scene description says the road itself is closed.

    ROADWork's "Fully Blocked" tag also covers closed sidewalks and side streets; the
    free-text description tells them apart.
    """
    for sentence in re.split(r"[.;]\s*", (description or "").lower()):
        if _CLOSED.search(sentence) and not _NOT_OWN_ROAD.search(sentence):
            return True
    return False


def select_eval_frames(images: list[dict], per_class: int = 50, seed: int = 7) -> list[dict]:
    """Pick a held-out verdict eval set, preferring unambiguous scene tags."""
    rng = random.Random(seed)
    images = sorted(images, key=lambda im: im["file_name"])

    def tags(im):
        return list((im.get("scene_level_tags") or {}).get("travel_alteration") or [])

    def take(pool, n):
        return rng.sample(pool, n) if len(pool) > n else list(pool)

    road_closed = [
        im
        for im in images
        if "Fully Blocked" in tags(im) and describes_own_road_closed(im.get("scene_description"))
    ]
    pure_blocked = [im for im in road_closed if tags(im) == ["Fully Blocked"]]
    mixed_blocked = [im for im in road_closed if tags(im) != ["Fully Blocked"]]
    blocked = take(pure_blocked, per_class)
    blocked += take(mixed_blocked, per_class - len(blocked))
    partial = take([im for im in images if tags(im) == ["Partially Blocked"]], per_class)
    clear = take([im for im in images if tags(im) == ["None"]], per_class)

    out = []
    for verdict, chosen in (("blocked", blocked), ("partial", partial), ("clear", clear)):
        for im in chosen:
            out.append(
                {
                    "file_name": im["file_name"],
                    "verdict": verdict,
                    "scene_description": im.get("scene_description") or "",
                    "city_name": im.get("city_name") or "",
                }
            )
    return out


def load_eval_manifest(path: Path) -> list[dict]:
    """Held-out verdict frames written by scripts/01_prepare_data.py."""
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"{path} not found. Run scripts/01_prepare_data.py first.")
    return json.loads(path.read_text())


def stale_item_ids(existing: list[dict], manifest: list[dict]) -> list[str]:
    """Ids of Opik dataset items that left the manifest or whose label changed."""
    wanted = {(m["file_name"], m["verdict"]) for m in manifest}
    return [
        item["id"]
        for item in existing
        if (item.get("file_name"), item.get("expected_verdict")) not in wanted
    ]
