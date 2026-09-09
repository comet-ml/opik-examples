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
    coverage: dict[str, int] = field(default_factory=dict)
    extrapolated_runs: int = 0


def _gpu_count(run: RunMetrics) -> int | None:
    return run.declared_num_gpus or run.detected_gpu_count


def flag_run(run: RunMetrics, low_util: float, idle_util: float) -> Finding:
    """Rule-based rightsizing verdict for one run; pure so dry-run output stays meaningful."""
    issues: list[str] = []
    severity = "ok"
    action = "No action — utilization is healthy."

    if run.gpu_util_mean is None:
        if run.detected_gpu_count or run.declared_num_gpus:
            declared = (
                f"Run declares {run.declared_num_gpus} devices ({run.scale_param}) but no "
                if run.declared_num_gpus
                else "No "
            )
            return Finding(
                run,
                "unknown",
                [f"{declared}GPU utilization series found."],
                "Enable system-metric logging so utilization can be audited.",
            )
        return Finding(
            run,
            "unknown",
            ["No GPU metrics and no declared hardware."],
            "Log the training scale (num_gpus / num_devices / nnodes) and enable system "
            "metrics for capacity planning.",
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

    if run.coverage == "rank0_sample":
        nodes = run.declared_nodes or (
            run.declared_num_gpus // run.detected_gpu_count
            if run.declared_num_gpus and run.detected_gpu_count
            else None
        )
        issues.append(
            f"Multi-node job: metrics cover 1 of {nodes} nodes "
            f"({run.detected_gpu_count} of {run.declared_num_gpus} GPUs) — utilization is "
            "extrapolated from the reporting node."
        )

    mismatch = bool(
        run.coverage != "rank0_sample"
        and run.declared_num_gpus
        and run.detected_gpu_count
        and run.declared_num_gpus != run.detected_gpu_count
    )
    if mismatch:
        severity = "high" if severity == "high" else "medium"
        issues.append(f"Declared {run.declared_num_gpus} GPUs but {run.detected_gpu_count} report metrics.")

    if run.cpu_util_mean is not None and run.cpu_util_mean > 80 and run.gpu_util_mean < low_util:
        issues.append(
            f"CPU at {run.cpu_util_mean}% while GPUs sit at {run.gpu_util_mean}% — "
            "likely dataloader/CPU-bound."
        )

    if run.declared_num_gpus is None and severity == "ok":
        return Finding(
            run,
            "unknown",
            ["Utilization is logged, but no scale parameter (num_gpus / num_devices / nnodes) is."],
            "Log the training scale so declared capacity can be compared with usage.",
        )

    if under_utilized:
        gpus = _gpu_count(run)
        target = max(1, round(gpus * run.gpu_util_mean / max(low_util, 1))) if gpus else 1
        gpu_type = f" {run.declared_gpu_type}" if run.declared_gpu_type else ""
        scope = " (fleet-wide estimate from the reporting node)" if run.coverage == "rank0_sample" else ""
        action = (
            f"Consider downsizing from {gpus} to ~{target}{gpu_type} GPUs{scope}, "
            "or batching jobs to raise utilization."
        )
    elif run.coverage == "rank0_sample" and severity == "ok":
        action = (
            "Utilization looks healthy on the reporting node; enable system-metric logging "
            "on every node to confirm fleet-wide."
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
    coverage: dict[str, int] = {"full": 0, "rank0_sample": 0, "none": 0}
    for finding in findings:
        run = finding.run
        coverage[run.coverage] = coverage.get(run.coverage, 0) + 1
        # WHY: for rank0_sample runs declared_num_gpus is the fleet total, so GPU-hour math
        # extrapolates the reporting node's utilization across the whole job.
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
        coverage=coverage,
        extrapolated_runs=coverage["rank0_sample"],
    )
    return summary, findings
