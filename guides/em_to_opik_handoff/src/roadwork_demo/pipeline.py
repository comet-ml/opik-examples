"""Inference pipeline: fine-tuned detector + vision-model verdict, traced in Opik.

Every detector trace carries the identifiers of the Comet experiment and registered model version
that produced the detector (see config.Handoff, resolved from the Model Registry), so Opik results
can be traced back to training.
"""

from __future__ import annotations

import threading
from functools import cache, lru_cache
from pathlib import Path
from typing import Literal

import opik
from opik import Attachment, opik_context

from roadwork_demo.config import REPO_ROOT, STOCK_VERSION, Handoff, get_settings, variant_tag
from roadwork_demo.images import data_uri, draw_overlay, encode_image
from roadwork_demo.llm import image_block, structured_json
from roadwork_demo.registry import resolve_handoff
from roadwork_demo.verdicts import VERDICT_SCHEMA, format_detections, parse_verdict

Variant = Literal["vlm_only", "detector_vlm"]
CONFIDENCE = 0.25

settings = get_settings()
# WHY: a YOLO model instance is not thread-safe; Opik evaluate() runs tasks in threads.
_predict_lock = threading.Lock()
_load_lock = threading.Lock()


@cache
def _resolve(detector: str) -> Handoff:
    return resolve_handoff(settings.workspace, settings.registry_model, detector, settings.project)


def get_handoff(detector: str | None = None) -> Handoff:
    """Handoff for "production", a registry version or "stock". None means DETECTOR_VERSION."""
    return _resolve(detector or settings.detector)


def registry_cache_dir(workspace: str, registry_model: str, version: str) -> Path:
    """Where weights downloaded from the Model Registry are kept between runs."""
    # WHY: the workspace is part of the key; the same model name and version can exist in two
    # workspaces that share one DATA_DIR, and their weights must never be mixed up.
    return settings.data_dir / "registry" / workspace / registry_model / version


@lru_cache(maxsize=2)
def _load_detector_cached(registry_model: str, version: str, workspace: str):
    from ultralytics import YOLO

    if version == STOCK_VERSION:
        return YOLO("yolo11s.pt")
    target = registry_cache_dir(workspace, registry_model, version)
    weights = next(target.rglob("*.pt"), None) if target.exists() else None
    if weights is None:
        from comet_ml import API

        target.mkdir(parents=True, exist_ok=True)
        # WHY: load what the registry serves, not the local runs folder, so the model under
        # evaluation is provably the registered version.
        API().get_model(workspace, registry_model).download(version, output_folder=str(target))
        weights = next(target.rglob("*.pt"))
    return YOLO(str(weights))


def load_detector(h: Handoff):
    # WHY: lru_cache does not serialize concurrent first calls; without the lock several
    # evaluate() threads would download the registry model into the same folder at once.
    with _load_lock:
        return _load_detector_cached(h.registry_model, h.model_version, h.comet_workspace)


@lru_cache(maxsize=1)
def get_verdict_prompt() -> opik.Prompt:
    """Verdict prompt, versioned in the Opik Prompt Library (new version only on change)."""
    text = (REPO_ROOT / "prompts" / "verdict.txt").read_text().strip()
    return opik.Opik().create_prompt(name=settings.prompt_name, prompt=text, project_name=settings.project)


def _overlay_path(handoff: Handoff, image_path: Path) -> Path:
    h = handoff
    return (
        settings.data_dir
        / "overlays"
        / h.comet_workspace
        / h.registry_model
        / h.model_version
        / image_path.name
    )


@opik.track(type="tool", name="detector", ignore_arguments=["handoff"])
def detect(image_path: str, handoff: Handoff) -> list[dict]:
    """Run the detector the handoff names. Span carries the EM / registry identifiers."""
    model = load_detector(handoff)
    with _predict_lock:
        result = model.predict(str(image_path), conf=CONFIDENCE, verbose=False)[0]
    detections = [
        {
            "label": result.names[int(cls)],
            "confidence": round(float(conf), 3),
            "box": [round(float(v), 1) for v in box],
        }
        for cls, conf, box in zip(result.boxes.cls, result.boxes.conf, result.boxes.xyxy, strict=True)
    ]
    overlay = draw_overlay(Path(image_path), detections, _overlay_path(handoff, Path(image_path)))
    opik_context.update_current_span(
        metadata=handoff.as_metadata() | {"n_detections": len(detections), "confidence": CONFIDENCE},
        tags=[handoff.model_tag()],
        attachments=[Attachment(data=str(overlay), content_type="image/jpeg")],
    )
    return detections


@opik.track(name="verdict", ignore_arguments=["image_b64", "overlay_b64"])
def verdict(image_b64: str, detections: list[dict] | None = None, overlay_b64: str | None = None) -> dict:
    """Ask the vision model for a structured verdict. `detections=None` means VLM only."""
    prompt = get_verdict_prompt()
    content = [{"type": "text", "text": "Camera frame:"}, image_block(image_b64)]
    if detections is not None:
        content.append({"type": "text", "text": f"Detector output:\n{format_detections(detections)}"})
        if overlay_b64:
            content += [
                {"type": "text", "text": "Same frame with detector boxes drawn:"},
                image_block(overlay_b64),
            ]
    content.append({"type": "text", "text": "Give your verdict."})

    opik_context.update_current_span(prompts=[prompt])
    parsed, raw = structured_json(
        settings.verdict_model, prompt.prompt, content, VERDICT_SCHEMA, max_tokens=2000
    )
    return parse_verdict(parsed, raw_text=raw)


def trace_identity(
    variant: Variant, handoff: Handoff | None, extra_tags: list[str] | None
) -> tuple[list[str], dict]:
    """Tags and metadata of a trace. Only a variant that ran a detector carries its identity."""
    tags = [variant_tag(variant), *(extra_tags or [])]
    metadata = {
        "variant": variant,
        "verdict_model": settings.verdict_model,
        "prompt_name": settings.prompt_name,
    }
    if variant == "vlm_only":
        return tags, metadata
    if handoff is None:
        raise ValueError(f"variant {variant} runs a detector and needs a handoff: pass get_handoff()")
    return [handoff.model_tag(), *tags], handoff.as_metadata() | metadata


@opik.track(name="road_obstruction_triage", project_name=settings.project, ignore_arguments=["handoff"])
def run_frame(
    image_path: str, variant: Variant, handoff: Handoff | None, extra_tags: list[str] | None = None
) -> dict:
    """One flagged frame -> verdict. Returns {verdict, reason, variant, detections}."""
    tags, metadata = trace_identity(variant, handoff, extra_tags)
    image_path = Path(image_path)
    image_b64 = encode_image(image_path)

    detections: list[dict] | None = None
    overlay_b64 = None
    if variant == "detector_vlm":
        detections = detect(str(image_path), handoff)
        overlay_b64 = encode_image(_overlay_path(handoff, image_path))

    result = verdict(image_b64, detections, overlay_b64)

    opik_context.update_current_trace(
        input={"image": data_uri(image_b64), "file_name": image_path.name},
        tags=tags,
        metadata=metadata,
        prompts=[get_verdict_prompt()],
    )
    return {
        "verdict": result["verdict"],
        "reason": result["reason"],
        "variant": variant,
        "detections": detections or [],
    }
