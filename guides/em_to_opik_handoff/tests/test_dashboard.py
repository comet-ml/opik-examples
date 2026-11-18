import json

from roadwork_demo.dashboard import TABLE_COLUMNS, VIEW_NAME, build_dashboard


def panels_of(view):
    return [panel for section in view.v3["sections"] for panel in section["panels"]]


def test_view_is_a_project_view_with_a_python_and_a_javascript_panel():
    view = build_dashboard("PYTHON CODE", "JS CODE")
    assert view.name == VIEW_NAME and view.layout_scope() == "project"
    kinds = [p["chartType"] for p in panels_of(view)]
    assert kinds.count("python") == 1 and kinds.count("javascript") == 1


def test_panel_sources_are_stored_in_the_view():
    by_kind = {p["chartType"]: p for p in panels_of(build_dashboard("PYTHON CODE", "JS CODE"))}
    assert by_kind["python"]["code"] == "PYTHON CODE"
    assert by_kind["javascript"]["code"]["code"] == "JS CODE"


def test_built_in_chart_shows_the_training_metric_per_epoch():
    lines = [p for p in panels_of(build_dashboard("p", "j")) if p["chartType"] == "line"]
    assert [p["metricNames"] for p in lines] == [["metrics/mAP50(B)"]]


def test_experiment_table_puts_training_and_downstream_columns_next_to_each_other():
    order = json.loads(build_dashboard("p", "j").table_state)["columnOrders"]
    shown = [c for c in order if c in TABLE_COLUMNS]
    assert shown == list(TABLE_COLUMNS)
    for column in ("metrics/mAP50(B)", "opik_verdict_accuracy", "opik_gate", "registry_model"):
        assert column in shown
    assert shown.index("metrics/mAP50(B)") + 1 == shown.index("opik_verdict_accuracy")


def test_every_panel_has_a_place_in_its_section_layout():
    for section in build_dashboard("p", "j").v3["sections"]:
        assert {entry["i"] for entry in section["layout"]} == {p["chartId"] for p in section["panels"]}
