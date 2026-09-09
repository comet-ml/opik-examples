from .analysis import CapacitySummary, Finding
from .collector import RunMetrics

SEVERITY_ORDER = {"high": 0, "medium": 1, "unknown": 2, "ok": 3}
COVERAGE_LABEL = {"full": "full", "rank0_sample": "rank-0 sample", "none": "—"}


def _fmt(value: object, suffix: str = "") -> str:
    return f"{value}{suffix}" if value is not None else "—"


def render_runs_table(runs: list[RunMetrics]) -> str:
    lines = [
        "| Project | Run | Declared GPUs | Reporting | Coverage | GPU util mean/peak | CPU mean | Hours |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        declared = _fmt(r.declared_num_gpus)
        if r.declared_nodes and r.declared_nodes > 1:
            declared += f" ({r.declared_nodes} nodes)"
        if r.declared_gpu_type:
            declared += f" × {r.declared_gpu_type}"
        util = f"{_fmt(r.gpu_util_mean, '%')} / {_fmt(r.gpu_util_peak, '%')}"
        lines.append(
            f"| {r.project} | {r.name or r.experiment_id} | {declared} "
            f"| {_fmt(r.detected_gpu_count)} | {COVERAGE_LABEL.get(r.coverage, r.coverage)} "
            f"| {util} | {_fmt(r.cpu_util_mean, '%')} | {_fmt(r.duration_hours)} |"
        )
    return "\n".join(lines)


def render_report(
    summary: CapacitySummary,
    findings: list[Finding],
    recommendations_md: str | None,
    source: str,
) -> str:
    coverage = summary.coverage
    coverage_line = (
        f"Metric coverage: **{coverage.get('full', 0)} full** · "
        f"**{coverage.get('rank0_sample', 0)} rank-0 sample** · "
        f"**{coverage.get('none', 0)} none**"
    )
    if summary.extrapolated_runs:
        coverage_line += (
            f" — GPU-hour figures extrapolate {summary.extrapolated_runs} multi-node "
            "run(s) from the reporting node"
        )
    parts = [
        "# GPU capacity audit",
        f"Source: **{source}** · Runs analyzed: **{summary.runs_analyzed}** · "
        f"Flagged: **{summary.runs_flagged}** · GPU-hours: **{summary.total_gpu_hours}** · "
        f"Estimated wasted GPU-hours: **{summary.est_wasted_gpu_hours}**",
        coverage_line,
        "",
        "## Runs",
        render_runs_table([f.run for f in findings]),
        "",
        "## Findings",
    ]
    flagged = sorted(
        (f for f in findings if f.severity != "ok"),
        key=lambda f: SEVERITY_ORDER.get(f.severity, 9),
    )
    if not flagged:
        parts.append("No runs flagged — utilization looks healthy at the current thresholds.")
    for f in flagged:
        parts.append(f"- **[{f.severity}] {f.run.project} / {f.run.name or f.run.experiment_id}**")
        parts.extend(f"  - {issue}" for issue in f.issues)
        parts.append(f"  - Suggested: {f.suggested_action}")

    if recommendations_md:
        parts += ["", "## LLM recommendations", recommendations_md]
    return "\n".join(parts)
