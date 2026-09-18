"""Post-training report: model quality + capacity efficiency for one project's runs.

The report trace carries the analysis payload as input and the recommendation as output,
so curated traces become directly replayable dataset items for offline evaluation.
"""

import urllib.parse
from dataclasses import dataclass

import opik
from opik import opik_context, url_helpers

from . import config, prompts
from .analysis import analyze
from .collector import RunMetrics, collect_runs
from .mcp_client import comet_session
from .recommender import write_recommendations
from .report import render_runs_table

SEVERITY_ORDER = {"high": 0, "medium": 1, "unknown": 2, "ok": 3}


@dataclass
class ReportResult:
    markdown: str
    trace_id: str | None


def _model_metrics_table(runs: list[RunMetrics]) -> str:
    keys = [
        k for k in config.MODEL_METRIC_KEYS if any((r.model_metrics or {}).get(k) is not None for r in runs)
    ]
    if not keys:
        return "No model-quality metrics found (looked for: " + ", ".join(config.MODEL_METRIC_KEYS) + ")."
    lines = [
        "| Run | " + " | ".join(keys) + " |",
        "|---|" + "---|" * len(keys),
    ]
    for r in runs:
        values = [(r.model_metrics or {}).get(k) for k in keys]
        cells = [f"{v:.3f}" if isinstance(v, float) else "-" for v in values]
        lines.append(f"| {r.name or r.experiment_id} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _links_section(runs: list[RunMetrics], trace_id: str | None) -> str:
    lines = ["## Review links"]
    lines += [f"- EM experiment: {r.name or r.experiment_id} - {r.url}" for r in runs if r.url]
    if trace_id and config.OPIK_WORKSPACE:
        path = urllib.parse.quote(
            f"{config.OPIK_WORKSPACE}/redirect/projects?name={config.OPIK_PROJECT_NAME}", safe=":/&?="
        )
        opik_project = urllib.parse.urljoin(url_helpers.get_ui_url(), path)
        lines.append(f"- Opik trace of this report: {opik_project} (trace id `{trace_id}`)")
    return "\n".join(lines)


@opik.track(name="training_report", project_name=config.OPIK_PROJECT_NAME)
async def build_report(
    workspace: str,
    project: str,
    experiment_ids: list[str] | None,
    synthetic: bool,
) -> ReportResult:
    """Collect the project's runs, then combine model metrics + capacity findings + links."""
    async with comet_session(synthetic) as session:
        runs = await collect_runs(session, workspace, [project], config.MAX_RUNS)
    if experiment_ids:
        wanted = set(experiment_ids)
        runs = [r for r in runs if r.experiment_id in wanted or (r.name or "") in wanted]

    summary, findings = analyze(runs, config.LOW_UTIL_PCT, config.IDLE_UTIL_PCT)
    recommendations = None if config.DRY_RUN else await write_recommendations(summary, findings)

    trace_data = None if config.DRY_RUN else opik_context.get_current_trace_data()
    trace_id = trace_data.id if trace_data else None

    flagged = sorted(
        (f for f in findings if f.severity != "ok"),
        key=lambda f: SEVERITY_ORDER.get(f.severity, 9),
    )
    parts = [
        f"# Training report - {project}",
        f"Runs: **{summary.runs_analyzed}** | Flagged: **{summary.runs_flagged}** | "
        f"GPU-hours: **{summary.total_gpu_hours}** | "
        f"Estimated wasted GPU-hours: **{summary.est_wasted_gpu_hours}**",
        "",
        "## Model quality",
        _model_metrics_table(runs),
        "",
        "## Capacity efficiency",
        render_runs_table(runs),
    ]
    for f in flagged:
        parts.append(f"- **[{f.severity}] {f.run.name or f.run.experiment_id}**: {f.suggested_action}")
    if recommendations:
        parts += ["", "## Recommendations", recommendations]
    parts += ["", _links_section(runs, trace_id)]
    markdown = "\n".join(parts)

    if not config.DRY_RUN:
        # Input/output carry the replayable payload: `curate` turns high-rated report
        # traces into dataset items, and `evaluate` re-runs the analyst on that input.
        opik_context.update_current_trace(
            input={"analysis_payload": prompts.analysis_payload(summary, findings)},
            output={"recommendations": recommendations or "", "report": markdown},
            tags=["capacity-planning", "training-report", "synthetic" if synthetic else "live"],
            metadata={
                "comet_workspace": workspace,
                "project": project,
                "runs_analyzed": summary.runs_analyzed,
                "runs_flagged": summary.runs_flagged,
                "model": config.GEN_MODEL,
            },
        )

    # --- Optional: post the summary to Slack ---------------------------------
    # Uncomment (and `uv add requests`) to notify a monitoring channel:
    #
    # import requests
    #
    # webhook = os.environ.get("SLACK_WEBHOOK_URL")
    # if webhook:
    #     requests.post(webhook, json={"text": markdown[:3000]}, timeout=10)
    # -------------------------------------------------------------------------

    return ReportResult(markdown=markdown, trace_id=trace_id)


def add_report_to_queue(trace_id: str) -> str | None:
    """Add the report trace to the review queue; returns the queue name when it worked."""
    client = opik.Opik(project_name=config.OPIK_PROJECT_NAME)
    client.flush()  # the trace must be persisted before the queue can reference it
    for queue in client.get_traces_annotation_queues():
        if queue.name == config.QUEUE_NAME:
            # WHY: queue.add_traces wants trace objects; the id-based REST op avoids a re-fetch.
            client.rest_client.annotation_queues.add_items_to_annotation_queue(id=queue.id, ids=[trace_id])
            return queue.name
    return None
