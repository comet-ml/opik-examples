from dataclasses import dataclass

import opik
from opik import opik_context

from . import config
from .analysis import CapacitySummary, Finding, analyze
from .collector import RunMetrics, collect_runs
from .mcp_client import comet_session
from .recommender import write_recommendations


@dataclass
class AuditResult:
    runs: list[RunMetrics]
    summary: CapacitySummary
    findings: list[Finding]
    recommendations_md: str | None


@opik.track(name="capacity_audit", project_name=config.OPIK_PROJECT_NAME)
async def run_audit(
    workspace: str,
    projects: list[str] | None,
    max_runs: int,
    synthetic: bool,
    low_util: float,
    idle_util: float,
) -> AuditResult:
    """The full pipeline: MCP sweep -> heuristics -> LLM report, all under one Opik trace."""
    async with comet_session(synthetic) as session:
        runs = await collect_runs(session, workspace, projects, max_runs)

    summary, findings = analyze(runs, low_util, idle_util)

    recommendations = None
    if not config.DRY_RUN:
        recommendations = await write_recommendations(summary, findings)
        opik_context.update_current_trace(
            tags=["capacity-planning", "comet-em", "mcp", "synthetic" if synthetic else "live"],
            metadata={
                "comet_workspace": workspace,
                "projects_scanned": sorted(summary.by_project),
                "runs_analyzed": summary.runs_analyzed,
                "runs_flagged": summary.runs_flagged,
                "total_gpu_hours": summary.total_gpu_hours,
                "est_wasted_gpu_hours": summary.est_wasted_gpu_hours,
                "coverage": summary.coverage,
                "extrapolated_runs": summary.extrapolated_runs,
                "thresholds": {"low_util_pct": low_util, "idle_util_pct": idle_util},
                "source": "synthetic" if synthetic else "live",
                "model": config.GEN_MODEL,
            },
        )

    return AuditResult(runs, summary, findings, recommendations)
