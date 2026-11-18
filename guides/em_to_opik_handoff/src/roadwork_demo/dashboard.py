"""The Comet project view that puts the training metric and the downstream result side by side."""

from __future__ import annotations

from comet_ml.api_objects.view import View
from comet_ml.views import Section, build_view, javascript_panel, line_panel, python_panel, table_state

from roadwork_demo.config import REPO_ROOT

VIEW_NAME = "Training vs downstream"
PANELS_DIR = REPO_ROOT / "panels"
TABLE_COLUMNS = (
    "Name",
    "registry_model",
    "metrics/mAP50(B)",
    "opik_verdict_accuracy",
    "opik_accuracy_blocked",
    "opik_gate",
    "dataset_artifact",
)


def build_dashboard(scorecard_code: str, chart_code: str) -> View:
    """Project view with the scorecard (Python panel), the per-class chart (JavaScript panel) and mAP."""
    return build_view(
        VIEW_NAME,
        sections=[
            Section(
                "Does a better detector make a better application?",
                [python_panel(code=scorecard_code, name="Training metric next to downstream result")],
                columns=1,
                height=2,
            ),
            Section(
                "Training in Comet EM, downstream in Opik",
                [
                    line_panel("metrics/mAP50(B)", name="Detector mAP50 per epoch (training)"),
                    javascript_panel(chart_code, name="Verdict accuracy per class, by detector version"),
                ],
                columns=2,
                height=2,
            ),
        ],
        table=table_state(columns=TABLE_COLUMNS, decimals=3, column_width=180),
    )
