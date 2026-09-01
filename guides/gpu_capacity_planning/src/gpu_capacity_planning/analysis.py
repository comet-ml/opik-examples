from dataclasses import dataclass, field
from typing import Any

import opik

from . import config
from .collector import RunMetrics


@dataclass
class Finding:
    run: RunMetrics
    severity: str  # "high" | "medium" | "ok" | "unknown"
    issues: list[str] = field(default_factory=list)
    suggested_action: str = ""


@dataclass
class CapacitySummary:
    runs_analyzed: int
    runs_flagged: int
    total_gpu_hours: float
    est_wasted_gpu_hours: float
    by_project: dict[str, dict[str, Any]]


def _gpu_count(run: RunMetrics) -> int | None:
    return run.declared_num_gpus or run.detected_gpu_count


def flag_run(run: RunMetrics, low_util: float, idle_util: float) -> Finding:
    """Rule-based rightsizing verdict for one run; pure so dry-run output stays meaningful."""
    issues: list[str] = []
    severity = "ok"
    action = "No action — utilization is healthy."

    if run.gpu_util_mean is None:
        if run.detected_gpu_count or run.declared_num_gpus:
            return Finding(
                run,
                "unknown",
                ["No GPU utilization series found."],
                "Enable system-metric logging so utilization can be audited.",
            )
        return Finding(
            run,
            "unknown",
            ["No GPU metrics and no declared hardware."],
            "Log num_gpus / gpu_type and enable system metrics for capacity planning.",
        )

    under_utilized = False
    if run.gpu_util_mean < idle_util:
        severity = "high"
        under_utilized = True
        issues.append(
            f"Mean GPU utilization {run.gpu_util_mean}% is below the idle threshold ({idle_util}%)."
        )
    elif run.gpu_util_mean < low_util:
        severity = "medium"
        under_utilized = True
        issues.append(
            f"Mean GPU utilization {run.gpu_util_mean}% is below the target threshold ({low_util}%)."
        )

    mismatch = bool(
        run.declared_num_gpus and run.detected_gpu_count and run.declared_num_gpus != run.detected_gpu_count
    )
    if mismatch:
        severity = "high" if severity == "high" else "medium"
        issues.append(
            f"Declared {run.declared_num_gpus} GPUs but only {run.detected_gpu_count} report metrics."
        )

    if run.cpu_util_mean is not None and run.cpu_util_mean > 80 and run.gpu_util_mean < low_util:
        issues.append(
            f"CPU at {run.cpu_util_mean}% while GPUs sit at {run.gpu_util_mean}% — "
            "likely dataloader/CPU-bound."
        )

    if run.declared_num_gpus is None and severity == "ok":
        return Finding(
            run,
            "unknown",
            ["Utilization is logged, but num_gpus / gpu_type parameters are not."],
            "Log num_gpus and gpu_type so declared capacity can be compared with usage.",
        )

    if under_utilized:
        gpus = _gpu_count(run)
        target = max(1, round(gpus * run.gpu_util_mean / max(low_util, 1))) if gpus else 1
        gpu_type = f" {run.declared_gpu_type}" if run.declared_gpu_type else ""
        action = (
            f"Consider downsizing from {gpus} to ~{target}{gpu_type} GPUs, "
            "or batching jobs to raise utilization."
        )
    elif mismatch:
        action = (
            f"Reconcile the declared num_gpus ({run.declared_num_gpus}) with the "
            f"{run.detected_gpu_count} GPUs actually reporting metrics."
        )

    return Finding(run, severity, issues, action)


@opik.track(project_name=config.OPIK_PROJECT_NAME)
def analyze(
    runs: list[RunMetrics], low_util: float, idle_util: float
) -> tuple[CapacitySummary, list[Finding]]:
    findings = [flag_run(run, low_util, idle_util) for run in runs]

    total_gpu_hours = 0.0
    wasted_gpu_hours = 0.0
    by_project: dict[str, dict[str, Any]] = {}
    for finding in findings:
        run = finding.run
        gpus = _gpu_count(run) or 0
        hours = run.duration_hours or 0.0
        gpu_hours = gpus * hours
        total_gpu_hours += gpu_hours
        if finding.severity in ("high", "medium") and run.gpu_util_mean is not None:
            wasted_gpu_hours += gpu_hours * (1 - run.gpu_util_mean / 100)

        stats = by_project.setdefault(run.project, {"runs": 0, "flagged": 0, "gpu_hours": 0.0})
        stats["runs"] += 1
        stats["gpu_hours"] = round(stats["gpu_hours"] + gpu_hours, 1)
        if finding.severity in ("high", "medium"):
            stats["flagged"] += 1

    summary = CapacitySummary(
        runs_analyzed=len(runs),
        runs_flagged=sum(1 for f in findings if f.severity in ("high", "medium")),
        total_gpu_hours=round(total_gpu_hours, 1),
        est_wasted_gpu_hours=round(wasted_gpu_hours, 1),
        by_project=by_project,
    )
    return summary, findings
