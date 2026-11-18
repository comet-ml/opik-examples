import pytest

from roadwork_demo.verdicts import format_detections, parse_verdict


def test_parse_valid():
    assert parse_verdict({"verdict": "blocked", "reason": "barrier across lane"}) == {
        "verdict": "blocked",
        "reason": "barrier across lane",
    }


@pytest.mark.parametrize(
    "tool_input",
    [None, {}, {"verdict": "temporary", "reason": "x"}, {"reason": "x"}, "not a dict"],
)
def test_parse_invalid_never_raises(tool_input):
    out = parse_verdict(tool_input, raw_text="free text")
    assert out["verdict"] == "invalid" and out["reason"]


def test_parse_invalid_without_any_text_still_has_reason():
    assert parse_verdict(None)["reason"]


def test_format_detections_empty():
    assert format_detections([]) == "no objects detected"


def test_format_detections_groups_by_class():
    s = format_detections(
        [
            {"label": "Cone", "confidence": 0.9, "box": [0, 0, 1, 1]},
            {"label": "Cone", "confidence": 0.5, "box": [0, 0, 1, 1]},
            {"label": "Drum", "confidence": 0.7, "box": [0, 0, 1, 1]},
        ]
    )
    assert "Cone x2" in s and "0.90" in s and "Drum x1" in s


@pytest.mark.parametrize(
    "trace_output,expected",
    [
        ({"verdict": "blocked", "reason": "x"}, "blocked"),  # pipeline called directly
        ({"output": {"verdict": "partial", "reason": "x"}}, "partial"),  # inside evaluate()
        ({"output": "text"}, None),
        ({}, None),
        (None, None),
    ],
)
def test_extract_verdict_from_trace_output(trace_output, expected):
    from roadwork_demo.verdicts import extract_verdict

    assert extract_verdict(trace_output) == expected


def _handoff():
    from roadwork_demo.config import Handoff

    return Handoff(
        "ws", "p", "abc", "https://x/abc", "roadwork-yolo11s", "1.0.0", "roadwork-yolo:1.0.0", 0.4, 0.2
    )


def test_detector_trace_carries_the_registry_identity():
    from roadwork_demo.pipeline import trace_identity

    tags, metadata = trace_identity("detector_vlm", _handoff(), ["source:x"])
    assert tags == ["detector:roadwork-yolo11s:1.0.0", "variant:detector_vlm", "source:x"]
    assert metadata["experiment_key"] == "abc" and metadata["variant"] == "detector_vlm"


def test_vlm_only_trace_carries_no_detector_identity():
    from roadwork_demo.pipeline import trace_identity

    for handoff in (None, _handoff()):
        tags, metadata = trace_identity("vlm_only", handoff, None)
        assert tags == ["variant:vlm_only"]
        assert "experiment_key" not in metadata and "model_version" not in metadata
        assert metadata["variant"] == "vlm_only"


def test_detector_variant_without_a_handoff_is_an_error():
    from roadwork_demo.pipeline import trace_identity

    with pytest.raises(ValueError, match="handoff"):
        trace_identity("detector_vlm", None, None)


def test_weights_and_overlays_are_cached_per_workspace():
    from roadwork_demo.pipeline import _overlay_path, registry_cache_dir, settings

    # WHY: the same model name and version can exist in two workspaces that share one DATA_DIR.
    cache = registry_cache_dir("ws", "roadwork-yolo11s", "1.0.0")
    assert cache == settings.data_dir / "registry" / "ws" / "roadwork-yolo11s" / "1.0.0"
    overlay = _overlay_path(_handoff(), __import__("pathlib").Path("/frames/a.jpg"))
    assert overlay == settings.data_dir / "overlays" / "ws" / "roadwork-yolo11s" / "1.0.0" / "a.jpg"
