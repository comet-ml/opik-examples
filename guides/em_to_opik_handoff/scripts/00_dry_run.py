"""Credentials-free self-check: image and prompt helpers on a synthetic frame, and the gate math.

Usage: uv run python scripts/00_dry_run.py
No network, no credentials, no detector weights. run.sh calls it after the unit tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from roadwork_demo.gate import decide, paired
from roadwork_demo.images import draw_overlay, encode_image
from roadwork_demo.verdicts import format_detections

FRAME_SIZE = (640, 360)
FAKE_DETECTIONS = [
    {"label": "cone", "confidence": 0.91, "box": [140.0, 220.0, 180.0, 300.0]},
    {"label": "barrier", "confidence": 0.78, "box": [300.0, 190.0, 520.0, 250.0]},
]
# Per-item verdict accuracy of two experiments on the same six dataset items.
CANDIDATE_SCORES = {"a": 1.0, "b": 1.0, "c": 1.0, "d": 0.0, "e": 1.0, "f": 1.0}
CURRENT_SCORES = {"a": 1.0, "b": 0.0, "c": 0.0, "d": 1.0, "e": 1.0, "f": 0.0}


def synthetic_frame(path: Path) -> Path:
    img = Image.new("RGB", FRAME_SIZE, (110, 110, 110))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, FRAME_SIZE[0], 150], fill=(150, 190, 230))
    draw.polygon([(140, 300), (160, 220), (180, 300)], fill=(240, 120, 20))
    draw.rectangle([300, 190, 520, 250], fill=(240, 200, 40))
    img.save(path, format="JPEG")
    return path


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        frame = synthetic_frame(Path(tmp) / "frame.jpg")
        print(f"[DRY RUN] synthetic frame: {frame.name}, {FRAME_SIZE[0]}x{FRAME_SIZE[1]}")
        b64 = encode_image(frame)
        print(f"[DRY RUN] encode_image: {len(b64)} base64 chars")
        overlay = draw_overlay(frame, FAKE_DETECTIONS, Path(tmp) / "overlay.jpg")
        print(f"[DRY RUN] draw_overlay: {overlay.name}, {overlay.stat().st_size} bytes")
        summary = format_detections(FAKE_DETECTIONS).replace("\n", "; ")
        print(f"[DRY RUN] format_detections: {summary}")
    result = paired(CANDIDATE_SCORES, CURRENT_SCORES)
    print(
        f"[DRY RUN] gate: candidate {result.mean_candidate:.3f} vs current {result.mean_current:.3f}, "
        f"delta {result.delta:+.3f}, won {result.wins} lost {result.losses}, "
        f"sign test p = {result.p_value:.3f} -> {decide(result.delta)}"
    )
    print("DRY RUN OK")


if __name__ == "__main__":
    main()
