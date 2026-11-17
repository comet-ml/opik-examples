"""Push fresh frames through the pipeline, as if flagged events were arriving in production.

Usage: uv run python scripts/09_simulate_traffic.py [--n 30]
Uses validation frames that are not in the eval set. With the online rule from
scripts/08_online_rule.py in place, the new traces get scored without any scoring script.
"""

from __future__ import annotations

import argparse
import random

import opik

from roadwork_demo.config import get_settings
from roadwork_demo.data import load_eval_manifest
from roadwork_demo.pipeline import get_handoff, run_frame

SOURCE_TAG = "source:simulated-traffic"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    s = get_settings()
    eval_names = {item["file_name"] for item in load_eval_manifest(s.eval_manifest_path)}
    pool = sorted(p for p in (s.data_dir / "yolo" / "images" / "val").iterdir() if p.name not in eval_names)
    frames = random.Random(args.seed).sample(pool, min(args.n, len(pool)))
    handoff = get_handoff()
    failed = 0
    for i, frame in enumerate(frames, start=1):
        try:
            result = run_frame(str(frame), "detector_vlm", handoff, extra_tags=[SOURCE_TAG])
        except Exception as exc:  # one bad frame must not stop the traffic
            failed += 1
            print(f"[{i}/{len(frames)}] {frame.name}: FAILED ({type(exc).__name__}: {exc})")
            continue
        print(f"[{i}/{len(frames)}] {frame.name}: {result['verdict']}")
    opik.flush_tracker()
    if failed:
        raise SystemExit(f"{failed} of {len(frames)} frames failed.")


if __name__ == "__main__":
    main()
