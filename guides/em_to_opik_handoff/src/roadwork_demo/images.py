"""Image helpers: downsized base64 JPEG for the vision model, detection overlays."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw


def _load_resized(path: Path, max_side: int) -> tuple[Image.Image, float]:
    img = Image.open(path).convert("RGB")
    scale = min(1.0, max_side / max(img.size))
    if scale < 1.0:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return img, scale


def encode_image(path: Path, max_side: int = 1024, quality: int = 85) -> str:
    """Base64 JPEG (no data-URI prefix), longest side at most `max_side`."""
    img, _ = _load_resized(Path(path), max_side)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def data_uri(b64_jpeg: str) -> str:
    return f"data:image/jpeg;base64,{b64_jpeg}"


def draw_overlay(
    path: Path, detections: list[dict], out_path: Path, max_side: int = 1024
) -> Path:
    """Draw detection boxes (pixel coords of the original image) on a downsized copy."""
    img, scale = _load_resized(Path(path), max_side)
    draw = ImageDraw.Draw(img)
    for d in detections:
        x1, y1, x2, y2 = (v * scale for v in d["box"])
        draw.rectangle([x1, y1, x2, y2], outline=(255, 40, 40), width=3)
        label = f"{d['label']} {d['confidence']:.2f}"
        tx, ty = x1 + 2, max(0, y1 - 12)
        draw.rectangle([tx - 2, ty, tx + 6 * len(label) + 2, ty + 11], fill=(255, 40, 40))
        draw.text((tx, ty), label, fill=(255, 255, 255))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="JPEG", quality=85)
    return out_path
