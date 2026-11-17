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
