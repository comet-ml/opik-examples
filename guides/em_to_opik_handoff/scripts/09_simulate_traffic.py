"""Push fresh frames through the pipeline, as if flagged events were arriving in production.

Usage: uv run python scripts/09_simulate_traffic.py [--n 30] [--detector production]
The default detector is whatever the Model Registry has in Production, so traffic after a
promote carries the promoted version with no config edit.
Uses validation frames that are not in the eval set. With the online rule from
scripts/08_online_rule.py in place, the new traces get scored without any scoring script.
"""

from __future__ import annotations

import argparse
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import opik

from roadwork_demo.config import exit_if_dry_run, get_settings
from roadwork_demo.data import load_eval_manifest
from roadwork_demo.pipeline import handoff_or_exit, load_detector, run_frame

SOURCE_TAG = "source:simulated-traffic"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--detector", default=None, help="production, a registry version or stock")
    args = ap.parse_args()

    s = get_settings()
    exit_if_dry_run(s, f"send {args.n} fresh frames through the pipeline into project '{s.project}'")
    eval_names = {item["file_name"] for item in load_eval_manifest(s.eval_manifest_path)}
    pool = sorted(p for p in (s.data_dir / "yolo" / "images" / "val").iterdir() if p.name not in eval_names)
    frames = random.Random(args.seed).sample(pool, min(args.n, len(pool)))
    handoff = handoff_or_exit(args.detector)
    print(f"Detector: {handoff.model_tag()}")
    load_detector(handoff)  # download registry weights once, before worker threads start

    def send(frame: Path) -> str | Exception:
        try:
            return run_frame(str(frame), "detector_vlm", handoff, extra_tags=[SOURCE_TAG])["verdict"]
        except Exception as exc:  # one bad frame must not stop the traffic
            return exc

    failed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, (frame, outcome) in enumerate(zip(frames, pool.map(send, frames), strict=True), start=1):
            if isinstance(outcome, Exception):
                failed += 1
                outcome = f"FAILED ({type(outcome).__name__}: {outcome})"
            print(f"[{i}/{len(frames)}] {frame.name}: {outcome}")
    opik.flush_tracker()
    if failed:
        raise SystemExit(f"{failed} of {len(frames)} frames failed.")


if __name__ == "__main__":
    main()
