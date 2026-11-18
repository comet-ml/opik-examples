import runpy
import sys
from types import ModuleType, SimpleNamespace

import pytest

from roadwork_demo.config import REPO_ROOT

PANEL = REPO_ROOT / "panels" / "scorecard.py"


def fake_experiment(name, others, metrics):
    return SimpleNamespace(
        name=name,
        get_others_summary=lambda: [{"name": k, "valueCurrent": v} for k, v in others.items()],
        get_metrics_summary=lambda: [{"name": k, "valueCurrent": v} for k, v in metrics.items()],
    )


BASELINE = fake_experiment(
    "yolo11s-baseline",
    {
        "registry_model": "roadwork-yolo11s:1.0.0",
        "opik_gate": "candidate 2.0.0: promote, delta=+0.062",
        "opik_experiment": "detector_vlm-1.0.0",
        "opik_experiment_url": "https://opik.example/exp1",
        "opik_vlm_only_accuracy": "0.6124",
    },
    {
        "metrics/mAP50(B)": "0.4142",
        "opik_verdict_accuracy": "0.5271",
        "opik_accuracy_blocked": "0.36",
        "opik_accuracy_partial": "0.6",
        "opik_accuracy_clear": "0.6897",
    },
)
CANDIDATE = fake_experiment(
    "yolo11s-candidate",
    {
        "registry_model": "roadwork-yolo11s:2.0.0",
        "opik_gate": "promote vs 1.0.0, delta=+0.062",
        "opik_experiment": "detector_vlm-2.0.0",
        "opik_experiment_url": "https://opik.example/exp2",
        "opik_vlm_only_accuracy": "0.6124",
    },
    {"metrics/mAP50(B)": "0.4888", "opik_verdict_accuracy": "0.5891", "opik_accuracy_blocked": "0.38"},
)
PREPARE_DATA = fake_experiment("prepare-data", {"Name": "prepare-data"}, {"sys.load.avg": "2.0"})
NOT_EVALUATED = fake_experiment(
    "yolo11s-next", {"registry_model": "roadwork-yolo11s:3.0.0"}, {"metrics/mAP50(B)": "0.51"}
)


class FakeModel:
    def find_versions(self):
        return ["2.0.0", "1.0.0"]

    def status(self, version):
        return {"2.0.0": "Production", "1.0.0": "Staging"}[version]


def run_panel(monkeypatch, experiments, registry_fails=False):
    """Execute the panel source the way Comet does, with the Comet and Streamlit modules faked."""
    shown = []

    class FakeAPI:
        def get_panel_experiments(self):
            return experiments

        def get_panel_workspace(self):
            return "ws"

        def get_model(self, workspace, name):
            if registry_fails:
                raise RuntimeError("registry not reachable")
            return FakeModel()

    comet = ModuleType("comet_ml")
    comet.API = FakeAPI
    streamlit = ModuleType("streamlit")
    streamlit.markdown = shown.append
    monkeypatch.setitem(sys.modules, "comet_ml", comet)
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    namespace = runpy.run_path(str(PANEL))
    return namespace, "\n".join(shown)


def test_one_row_per_registered_run_in_version_order(monkeypatch):
    namespace, _ = run_panel(monkeypatch, [CANDIDATE, PREPARE_DATA, BASELINE])
    rows = namespace["scorecard_rows"]([CANDIDATE, PREPARE_DATA, BASELINE])
    assert [(r["version"], r["run"]) for r in rows] == [
        ("1.0.0", "yolo11s-baseline"),
        ("2.0.0", "yolo11s-candidate"),
    ]
    assert rows[0]["map50"] == pytest.approx(0.4142)
    assert rows[0]["vs_no_detector"] == pytest.approx(0.5271 - 0.6124)


def test_panel_shows_training_and_downstream_numbers_side_by_side(monkeypatch):
    _, text = run_panel(monkeypatch, [BASELINE, CANDIDATE])
    baseline_row = next(line for line in text.splitlines() if line.startswith("| 1.0.0"))
    for cell in ("Staging", "yolo11s-baseline", "0.414", "0.527", "-0.085", "0.36", "0.60", "0.69"):
        assert cell in baseline_row
    assert "[detector_vlm-1.0.0](https://opik.example/exp1)" in baseline_row
    assert "candidate 2.0.0: promote, delta=+0.062" in baseline_row
    candidate_row = next(line for line in text.splitlines() if line.startswith("| 2.0.0"))
    assert "Production" in candidate_row and "-0.023" in candidate_row
    assert "0.612" in text  # the no-detector reference


def test_a_registered_run_without_opik_results_says_so_instead_of_showing_zeros(monkeypatch):
    _, text = run_panel(monkeypatch, [NOT_EVALUATED])
    row = next(line for line in text.splitlines() if line.startswith("| 3.0.0"))
    assert "0.510" in row and "not evaluated in Opik yet" in row and "0.000" not in row


def test_panel_still_renders_when_the_registry_cannot_be_read(monkeypatch):
    _, text = run_panel(monkeypatch, [BASELINE], registry_fails=True)
    assert "| 1.0.0 | unknown |" in text


def test_panel_explains_an_empty_page(monkeypatch):
    _, text = run_panel(monkeypatch, [PREPARE_DATA])
    assert "No registered training run" in text and "03_register.py" in text
