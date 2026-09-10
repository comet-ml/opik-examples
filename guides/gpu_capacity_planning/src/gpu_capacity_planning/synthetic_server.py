"""Local stand-in for `uvx comet-mcp`: same five tools, same response shapes, sample data.

Lets the audit and agent run with zero credentials while exercising the real MCP client path.
"""

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

# CAPACITY_SAMPLE_DATA lets you point the synthetic server at your own exported
# snapshot (same JSON shape as data/sample_runs.json) and audit it offline.
DATA_PATH = Path(
    os.environ.get("CAPACITY_SAMPLE_DATA", Path(__file__).resolve().parents[2] / "data" / "sample_runs.json")
)
DATA = json.loads(DATA_PATH.read_text())
STEP = 100

mcp = MCPServer("comet-mcp-synthetic")


def _find_experiment(experiment_id: str) -> tuple[str, dict[str, Any]]:
    for project, pdata in DATA["projects"].items():
        exp = pdata["experiments"].get(experiment_id)
        if exp:
            return project, exp
    raise ValueError(f"Experiment with ID '{experiment_id}' not found.")


def _jitter(base: float, index: int) -> float:
    # WHY: deterministic per-GPU variation so 64 series aren't byte-identical.
    return max(0.0, min(100.0, base + ((index * 7) % 5) - 2))


def _series(profile: list[float], index: int) -> list[list[float]]:
    return [[i * STEP, _jitter(v, index)] for i, v in enumerate(profile)]


def _metric_names(exp: dict[str, Any]) -> dict[str, list[list[float]]]:
    gpu = exp.get("gpu_series", {})
    count = gpu.get("count", 0)
    metrics: dict[str, list[list[float]]] = {}
    for i in range(count):
        # WHY: exported snapshots may log utilization without memory (or vice versa);
        # an empty series must not become an advertised metric.
        for kind, name in (("utilization", "gpu_utilization"), ("memory", "memory_utilization")):
            series = _series(gpu.get(kind, []), i)
            if series:
                metrics[f"sys.gpu.{i}.{name}"] = series
    if exp.get("cpu_series"):
        metrics["sys.cpu.percent.avg"] = _series(exp["cpu_series"], 0)
    return metrics


@mcp.tool()
def list_projects(
    workspace: str | None = None,
    prefix: str | None = None,
    page: int | None = 1,
    page_size: int | None = 10,
) -> dict[str, Any]:
    """List project names in a Comet ML workspace."""
    projects = list(DATA["projects"])
    return {
        "workspace": workspace or DATA["workspace"],
        "projects": projects,
        "total_count": len(projects),
        "filtered_count": len(projects),
        "page_info": {
            "page": 1,
            "page_size": len(projects),
            "has_more": False,
            "returned_count": len(projects),
        },
    }


@mcp.tool()
def list_experiments(
    workspace: str | None = None,
    project_name: str | None = None,
    page: int | None = 1,
    page_size: int | None = 10,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> dict[str, Any]:
    """List experiments in a project."""
    pdata = DATA["projects"].get(project_name or "", {"experiments": {}})
    return {
        "workspace": workspace or DATA["workspace"],
        "project": project_name,
        "experiments": [
            {
                "id": exp_id,
                "name": exp["name"],
                "status": exp["status"],
                "created_at": exp["created_at"],
                "description": exp.get("description"),
            }
            for exp_id, exp in pdata["experiments"].items()
        ],
    }


@mcp.tool()
def get_experiment_details(experiment_id: str) -> dict[str, Any]:
    """Get detailed information about an experiment, including metric and parameter names."""
    project, exp = _find_experiment(experiment_id)
    metrics = _metric_names(exp)
    return {
        "id": experiment_id,
        "url": f"https://www.comet.com/{DATA['workspace']}/{project}/{experiment_id}",
        "name": exp["name"],
        "status": exp["status"],
        "created_at": exp["created_at"],
        "updated_at": exp["updated_at"],
        "description": exp.get("description"),
        "metrics": [{"name": name, "value": series[-1][1]} for name, series in metrics.items()],
        "parameters": [{"name": k, "value": v} for k, v in exp.get("parameters", {}).items()],
        "others": [],
    }


@mcp.tool()
def get_experiment_parameters(experiment_id: str) -> dict[str, Any]:
    """Get experiment parameters and configuration settings."""
    _, exp = _find_experiment(experiment_id)
    parameters = dict(exp.get("parameters", {}))
    return {
        "id": experiment_id,
        "name": exp["name"],
        "parameters": parameters,
        "parameter_count": len(parameters),
    }


@mcp.tool()
def get_experiment_metric_data(
    experiment_ids: list[str],
    metric_names: list[str],
    x_axis: str | None = None,
) -> dict[str, Any]:
    """Get metric series for specific experiments."""
    experiments: dict[str, Any] = {}
    for exp_id in experiment_ids:
        _, exp = _find_experiment(exp_id)
        available = _metric_names(exp)
        experiments[exp_id] = {
            name: {"metric_name": name, "x_axis": "steps", "data": available[name]}
            for name in metric_names
            if name in available
        }
    return {"experiment_ids": experiment_ids, "x_axis": "steps", "experiments": experiments}


if __name__ == "__main__":
    mcp.run()
