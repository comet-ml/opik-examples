"""Comet Python panel: the training metric of every registered run next to its downstream result.

Runs inside Comet, not locally. scripts/10_em_dashboard.py stores this file in the project view.
"""

import streamlit as st
from comet_ml import API

CLASSES = ("blocked", "partial", "clear")
NOT_EVALUATED = "not evaluated in Opik yet"


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def cell(value, digits=3, signed=False):
    if value is None:
        return "-"
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def version_key(row):
    return [int(part) if part.isdigit() else 0 for part in row["version"].split(".")]


def scorecard_rows(experiments):
    """One row per experiment that was registered in the Model Registry, oldest version first."""
    rows = []
    for experiment in experiments:
        others = {o["name"]: o.get("valueCurrent") for o in experiment.get_others_summary()}
        registered = others.get("registry_model")
        if not registered:
            continue
        metrics = {m["name"]: m.get("valueCurrent") for m in experiment.get_metrics_summary()}
        model, _, version = registered.rpartition(":")
        accuracy = number(metrics.get("opik_verdict_accuracy"))
        reference = number(others.get("opik_vlm_only_accuracy"))
        both = accuracy is not None and reference is not None
        rows.append(
            {
                "model": model,
                "version": version,
                "run": experiment.name,
                "map50": number(metrics.get("metrics/mAP50(B)")),
                "accuracy": accuracy,
                "reference": reference,
                "vs_no_detector": accuracy - reference if both else None,
                "per_class": [number(metrics.get(f"opik_accuracy_{c}")) for c in CLASSES],
                "gate": others.get("opik_gate"),
                "opik_experiment": others.get("opik_experiment"),
                "opik_url": others.get("opik_experiment_url"),
            }
        )
    return sorted(rows, key=version_key)


def registry_statuses(api, workspace, rows):
    statuses = {}
    for name in {row["model"] for row in rows}:
        # WHY: the status is a nice-to-have here; a registry that cannot be read must not blank
        # the whole panel.
        try:
            model = api.get_model(workspace, name)
            for version in model.find_versions():
                statuses[(name, version)] = model.status(version)
        except Exception:
            continue
    return statuses


def render(rows, statuses):
    if not rows:
        return (
            "No registered training run among the experiments on this page. "
            "Register one with `scripts/03_register.py`, then evaluate it with "
            "`scripts/05_run_experiments.py`."
        )
    lines = [
        "#### Does a better detector make a better application?",
        "",
        "Training metric from Comet EM (mAP50) next to the downstream metric from Opik (verdict "
        "accuracy on the same held-out frames), for every training run in the Model Registry.",
        "",
        "| Registry version | Status | Training run | mAP50 | Verdict accuracy | vs no detector "
        "| blocked | partial | clear | Gate | Opik experiment |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        if row["accuracy"] is None:
            downstream = [NOT_EVALUATED, "-", "-", "-", "-", "-", "-"]
        else:
            link = f"[{row['opik_experiment']}]({row['opik_url']})" if row["opik_url"] else "-"
            downstream = [
                cell(row["accuracy"]),
                cell(row["vs_no_detector"], signed=True),
                *(cell(value, digits=2) for value in row["per_class"]),
                row["gate"] or "not gated yet",
                link,
            ]
        cells = [
            row["version"],
            statuses.get((row["model"], row["version"]), "unknown"),
            row["run"],
            cell(row["map50"]),
            *downstream,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    reference = next((row["reference"] for row in rows if row["reference"] is not None), None)
    if reference is not None:
        lines += [
            "",
            f"No detector at all (`vlm_only`): {cell(reference)} verdict accuracy. A higher mAP50 "
            "means a better detector; only the Opik columns say whether the application got better.",
        ]
    return "\n".join(lines)


api = API()
rows = scorecard_rows(api.get_panel_experiments())
st.markdown(render(rows, registry_statuses(api, api.get_panel_workspace(), rows)))
