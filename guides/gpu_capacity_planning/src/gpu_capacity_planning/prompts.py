import json

from .analysis import CapacitySummary, Finding

ANALYST_SYSTEM_PROMPT = """\
You are a GPU capacity-planning analyst. You receive utilization findings for machine-learning \
training runs: declared scale (num_gpus / num_devices / nnodes), measured GPU/CPU utilization, \
durations, and rule-based flags. Coverage semantics: coverage=rank0_sample means the run is a \
multi-node job whose system metrics come from the rank-0 node only - its utilization and \
GPU-hours are single-node samples extrapolated to the declared device count, so present those as \
estimates and recommend enabling system-metric logging on every node. coverage=none means the \
run declares scale but logs no utilization at all. Write a rightsizing report in Markdown with \
three sections: \
**Summary** (2-3 sentences, lead with the estimated wasted GPU-hours), \
**Per-run recommendations** (one bullet per flagged run: what to change and why, quantified), \
**Next steps** (instrumentation or scheduling improvements). \
Be specific and quantitative; recommend concrete GPU counts. Do not invent runs or numbers."""

AGENT_SYSTEM_PROMPT = """\
You are a GPU capacity-planning assistant with tool access to a Comet experiment-management \
workspace. Answer the user's question by calling the tools - list projects and experiments, then \
pull details, parameters, and system-metric series (sys.gpu.N.gpu_utilization and friends) for \
the runs that matter. Training scale may be declared under different parameter names \
(num_gpus, num_devices, world_size, nnodes); multi-node jobs often report system metrics from \
the rank-0 node only, so treat per-node series as a sample of the fleet and say so. Compare \
declared scale against measured utilization and answer quantitatively. Keep tool calls focused; \
do not sweep everything when a subset answers the question."""


def analysis_payload(summary: CapacitySummary, findings: list[Finding]) -> str:
    """Compact JSON the analyst model reads; flagged/unknown runs only, to keep tokens bounded."""
    return json.dumps(
        {
            "summary": {
                "runs_analyzed": summary.runs_analyzed,
                "runs_flagged": summary.runs_flagged,
                "total_gpu_hours": summary.total_gpu_hours,
                "est_wasted_gpu_hours": summary.est_wasted_gpu_hours,
                "coverage": summary.coverage,
                "extrapolated_runs": summary.extrapolated_runs,
                "by_project": summary.by_project,
            },
            "findings": [
                {
                    "project": f.run.project,
                    "run": f.run.name or f.run.experiment_id,
                    "severity": f.severity,
                    "declared_num_gpus": f.run.declared_num_gpus,
                    "declared_gpu_type": f.run.declared_gpu_type,
                    "declared_nodes": f.run.declared_nodes,
                    "scale_param": f.run.scale_param,
                    "coverage": f.run.coverage,
                    "detected_gpu_count": f.run.detected_gpu_count,
                    "gpu_util_mean_pct": f.run.gpu_util_mean,
                    "gpu_util_peak_pct": f.run.gpu_util_peak,
                    "cpu_util_mean_pct": f.run.cpu_util_mean,
                    "duration_hours": f.run.duration_hours,
                    "issues": f.issues,
                    "rule_based_action": f.suggested_action,
                }
                for f in findings
                if f.severity != "ok"
            ],
        },
        indent=2,
    )
