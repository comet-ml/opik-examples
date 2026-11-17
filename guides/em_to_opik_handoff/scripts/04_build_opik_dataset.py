"""Create the Opik verdict dataset from the held-out eval manifest.

Usage: uv run python scripts/04_build_opik_dataset.py [--limit N]
--limit N writes a small stratified subset to "<dataset>-dev" for quick iteration.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import opik

from roadwork_demo.config import get_settings, load_handoff
from roadwork_demo.data import load_eval_manifest, stale_item_ids
from roadwork_demo.images import data_uri, encode_image

ATTRIBUTION = (
    "Frames and scene labels from the CMU ROADWork dataset (ODC-By 1.0), "
    "https://kilthub.cmu.edu/articles/dataset/ROADWork_Data/26093197"
)


def stratified(manifest: list[dict], limit: int) -> list[dict]:
    by_verdict = defaultdict(list)
    for item in manifest:
        by_verdict[item["verdict"]].append(item)
    per = max(1, limit // len(by_verdict))
    return [item for items in by_verdict.values() for item in items[:per]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    s = get_settings()
    manifest = load_eval_manifest(s.eval_manifest_path)
    name = s.opik_dataset
    if args.limit:
        manifest = stratified(manifest, args.limit)
        name = s.dev_dataset

    artifact = "unknown"
    if s.handoff_path.exists():
        artifact = load_handoff(s.handoff_path).dataset_artifact

    client = opik.Opik()
    dataset = client.get_or_create_dataset(
        name=name,
        description=f"Held-out frames with human verdict labels. Source artifact: {artifact}. {ATTRIBUTION}",
    )
    # Safe to re-run: Opik de-duplicates identical items, and items that left the manifest or
    # changed label are removed so the dataset always mirrors the manifest.
    stale = stale_item_ids(dataset.get_items(), manifest)
    if stale:
        dataset.delete(stale)
        print(f"Removed {len(stale)} item(s) no longer in the manifest")
    dataset.insert(
        [
            {
                "image": data_uri(encode_image(Path(item["path"]))),
                "file_name": item["file_name"],
                "expected_verdict": item["verdict"],
                "scene_description": item["scene_description"],
                "city_name": item["city_name"],
            }
            for item in manifest
        ]
    )
    client.flush()
    print(f"Dataset '{name}': {len(manifest)} items")


if __name__ == "__main__":
    main()
