from unittest.mock import MagicMock

import pytest
from opik.evaluation.metrics import GEval, score_result
from opik.evaluation.metrics.base_metric import BaseMetric

import metrics as defs
import score_traces as runner
from metrics import Eval, ExactMatch
from paths import MissingField, resolve_path, resolve_variables
from utils import seed_traces


def _trace_data():
    return {
        "input": {"question": "What is 2+2?"},
        "output": {"answer": "4", "context": ["math basics"]},
        "metadata": {"model": "gpt-4o"},
    }


def test_resolve_path_nested_value():
    assert resolve_path(_trace_data(), "input.question") == "What is 2+2?"


def test_resolve_path_list_value_passthrough():
    assert resolve_path(_trace_data(), "output.context") == ["math basics"]


def test_resolve_path_metadata_dotted():
    assert resolve_path(_trace_data(), "metadata.model") == "gpt-4o"


def test_resolve_path_missing_key_raises():
    with pytest.raises(MissingField):
        resolve_path(_trace_data(), "output.missing")


def test_resolve_path_missing_toplevel_raises():
    with pytest.raises(MissingField):
        resolve_path({"input": None, "output": {}, "metadata": {}}, "input.question")


def test_resolve_variables_maps_all_params():
    result = resolve_variables(
        _trace_data(),
        {"input": "input.question", "output": "output.answer", "context": "output.context"},
    )
    assert result == {"input": "What is 2+2?", "output": "4", "context": ["math basics"]}


def test_exact_match_hit():
    r = ExactMatch().score(output="4", reference="4")
    assert r.value == 1.0
    assert r.name == "exact_match"
    assert r.reason  # non-empty explanation


def test_exact_match_miss():
    r = ExactMatch().score(output="5", reference="4")
    assert r.value == 0.0
    assert r.reason


def test_definitions_shape():
    assert len(defs.EVALS) == 3
    names = {e.name for e in defs.EVALS}
    assert names == {"hallucination", "relevance", "exact_match"}


def test_each_eval_is_wellformed():
    for e in defs.EVALS:
        assert isinstance(e.name, str) and e.name
        assert isinstance(e.metric, BaseMetric)
        assert isinstance(e.variables, dict) and e.variables


def test_exact_match_eval_uses_python_metric():
    e = next(e for e in defs.EVALS if e.name == "exact_match")
    assert e.variables == {"output": "output.answer", "reference": "input.expected"}


def test_seed_dataset_has_good_and_bad():
    assert len(seed_traces.SEED_TRACES) >= 8
    # Every seed trace has the fields the EVALS variable mappings read (metrics.py).
    for t in seed_traces.SEED_TRACES:
        assert set(t["input"]) >= {"question", "expected"}
        assert set(t["output"]) >= {"answer", "context"}
    answers = {t["output"]["answer"] for t in seed_traces.SEED_TRACES}
    expected = {t["input"]["expected"] for t in seed_traces.SEED_TRACES}
    # At least one exact-match hit and one miss, so scores show a spread.
    assert answers & expected            # some hits
    assert any(t["output"]["answer"] != t["input"]["expected"] for t in seed_traces.SEED_TRACES)


class _StubTrace:
    def __init__(self, id, input, output):
        self.id, self.input, self.output, self.metadata = id, input, output, {}


def _good_metric(value, reason="ok"):
    m = MagicMock()
    m.score.return_value = score_result.ScoreResult(value=value, name="m", reason=reason)
    return m


def test_score_trace_maps_and_preserves_reason():
    ev = Eval(name="m", metric=_good_metric(1.0, "grounded"),
              variables={"output": "output.answer"})
    trace = _StubTrace("t1", {"question": "q"}, {"answer": "a"})
    scores = runner.score_trace(trace, [ev])
    assert scores == [{"id": "t1", "name": "m", "value": 1.0, "reason": "grounded"}]
    ev.metric.score.assert_called_once_with(output="a")


def test_score_trace_skips_missing_field():
    ev = Eval(name="m", metric=_good_metric(1.0), variables={"output": "output.MISSING"})
    trace = _StubTrace("t1", {}, {"answer": "a"})
    assert runner.score_trace(trace, [ev]) == []          # skipped, no raise


def test_score_trace_isolates_failing_eval():
    boom = MagicMock()
    boom.score.side_effect = RuntimeError("judge exploded")
    ev_bad = Eval(name="bad", metric=boom, variables={"output": "output.answer"})
    ev_ok = Eval(name="ok", metric=_good_metric(0.5), variables={"output": "output.answer"})
    trace = _StubTrace("t1", {}, {"answer": "a"})
    scores = runner.score_trace(trace, [ev_bad, ev_ok])
    assert [s["name"] for s in scores] == ["ok"]           # bad skipped, ok survives


def test_window_filter_is_oql_start_time():
    f = runner.window_filter(2)
    assert f.startswith('start_time >= "') and f.endswith('Z"')


def test_geval_payload_labels_all_fields():
    payload = runner.geval_payload({"input": "What is 2+2?", "output": "4"})
    assert "INPUT: What is 2+2?" in payload
    assert "OUTPUT: 4" in payload


def test_score_trace_routes_geval_through_payload():
    g = GEval(model="gpt-4o", name="relevance",
              task_introduction="t", evaluation_criteria="c")
    g.score = MagicMock(return_value=score_result.ScoreResult(value=1.0, name="relevance", reason="ok"))
    ev = Eval(name="relevance", metric=g,
              variables={"input": "input.question", "output": "output.answer"})
    trace = _StubTrace("t1", {"question": "q?"}, {"answer": "a"})
    scores = runner.score_trace(trace, [ev])
    assert scores == [{"id": "t1", "name": "relevance", "value": 1.0, "reason": "ok"}]
    # GEval got ONE labeled payload string, not separate kwargs
    called = g.score.call_args
    assert list(called.kwargs) == ["output"]
    assert "INPUT: q?" in called.kwargs["output"]
    assert "OUTPUT: a" in called.kwargs["output"]
