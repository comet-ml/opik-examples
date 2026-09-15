import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import opik
from mcp import ClientSession

from . import config
from .mcp_client import call_tool

GPU_UTIL_RE = re.compile(r"^sys\.gpu\.(\d+)\.gpu_utilization$")
GPU_MEM_RE = re.compile(r"^sys\.gpu\.(\d+)\.memory_utilization$")
CPU_METRIC = "sys.cpu.percent.avg"


@dataclass
class RunMetrics:
    workspace: str
    project: str
    experiment_id: str
    name: str | None = None
    url: str | None = None
    declared_num_gpus: int | None = None
    declared_gpu_type: str | None = None
    scale_param: str | None = None
    declared_nodes: int | None = None
    duration_hours: float | None = None
    detected_gpu_count: int | None = None
    coverage: str = "none"  # "full" | "rank0_sample" | "none"
    gpu_util_mean: float | None = None
    gpu_util_peak: float | None = None
    gpu_mem_peak_pct: float | None = None
    cpu_util_mean: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_int(value: Any) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def flatten_params(raw: Any) -> dict[str, Any]:
    """Normalize parameters from either shape: {name: value} or [{name, value|valueCurrent}]."""
    if isinstance(raw, dict):
        return dict(raw)
    flat: dict[str, Any] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "name" in item:
                flat[item["name"]] = item.get("value", item.get("valueCurrent"))
    return flat


def declared_scale(params: dict[str, Any]) -> tuple[int | None, str | None, int | None]:
    """(total devices, param key used, node count) from whichever scale params the run logs."""
    devices, key = None, None
    for candidate in config.DEVICE_PARAM_KEYS:
        devices = _to_int(params.get(candidate))
        if devices:
            key = candidate
            break
    nodes = None
    for candidate in config.NODE_PARAM_KEYS:
        nodes = _to_int(params.get(candidate))
        if nodes:
            key = key or candidate
            break
    return devices, key, nodes


def resolve_coverage(run: "RunMetrics") -> str:
    """How much of the declared fleet the metric series cover.

    Multi-node jobs typically log ONE experiment whose system metrics come from the
    rank-0 node only, so declared=64 with 8 GPUs reporting usually means an 8-node job,
    not a misconfiguration. Divisibility is the tell.
    """
    detected = run.detected_gpu_count
    if not detected:
        return "none"
    declared = run.declared_num_gpus
    if run.declared_nodes and run.declared_nodes > 1:
        return "rank0_sample"
    if declared and declared > detected and declared % detected == 0:
        return "rank0_sample"
    return "full"


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def duration_hours(details: dict[str, Any]) -> float | None:
    millis = details.get("durationMillis")
    if millis is not None:
        return round(_to_float(millis) / 3.6e6, 2) if _to_float(millis) else None
    start = _parse_dt(details.get("created_at"))
    end = _parse_dt(details.get("updated_at"))
    if start and end and end > start:
        return round((end - start).total_seconds() / 3600, 2)
    return None


def series_stats(data: Any) -> tuple[float | None, float | None]:
    """(mean, peak) over a metric series of [x, y] pairs (dict points tolerated)."""
    values: list[float] = []
    for point in data or []:
        y = None
        if isinstance(point, list | tuple) and len(point) >= 2:
            y = _to_float(point[1])
        elif isinstance(point, dict):
            y = _to_float(point.get("y", point.get("value")))
        if y is not None:
            values.append(y)
    if not values:
        return None, None
    return round(sum(values) / len(values), 1), round(max(values), 1)


def _metric_names(details: dict[str, Any]) -> list[str]:
    return [m.get("name", "") for m in details.get("metrics", []) if isinstance(m, dict)]


@opik.track(project_name=config.OPIK_PROJECT_NAME)
async def fetch_run(session: ClientSession, workspace: str, project: str, experiment_id: str) -> RunMetrics:
    """Pull one run's declared hardware and system-metric series through the MCP tools."""
    details = await call_tool(session, "get_experiment_details", {"experiment_id": experiment_id})
    params_resp = await call_tool(session, "get_experiment_parameters", {"experiment_id": experiment_id})

    params = flatten_params(params_resp.get("parameters"))
    params.update(flatten_params(details.get("others")))
    devices, scale_key, nodes = declared_scale(params)

    run = RunMetrics(
        workspace=workspace,
        project=project,
        experiment_id=experiment_id,
        name=details.get("name"),
        url=details.get("url"),
        declared_num_gpus=devices,
        declared_gpu_type=params.get("gpu_type") or None,
        scale_param=scale_key,
        declared_nodes=nodes,
        duration_hours=duration_hours(details),
    )

    names = _metric_names(details)
    gpu_util_names = [n for n in names if GPU_UTIL_RE.match(n)]
    gpu_mem_names = [n for n in names if GPU_MEM_RE.match(n)]
    run.detected_gpu_count = len(gpu_util_names) or None
    if run.declared_num_gpus is None and nodes and run.detected_gpu_count:
        # Only the node count is declared: total = nodes x GPUs visible on the reporting node.
        run.declared_num_gpus = nodes * run.detected_gpu_count
    run.coverage = resolve_coverage(run)

    wanted = gpu_util_names + gpu_mem_names + ([CPU_METRIC] if CPU_METRIC in names else [])
    if not wanted:
        return run

    metric_data = await call_tool(
        session,
        "get_experiment_metric_data",
        {"experiment_ids": [experiment_id], "metric_names": wanted},
    )
    series = metric_data.get("experiments", {}).get(experiment_id, {})

    util_means, util_peaks, mem_peaks = [], [], []
    for name, metric in series.items():
        mean, peak = series_stats(metric.get("data") if isinstance(metric, dict) else None)
        if mean is None:
            continue
        if GPU_UTIL_RE.match(name):
            util_means.append(mean)
            util_peaks.append(peak)
        elif GPU_MEM_RE.match(name):
            mem_peaks.append(peak)
        elif name == CPU_METRIC:
            run.cpu_util_mean = mean

    if util_means:
        run.gpu_util_mean = round(sum(util_means) / len(util_means), 1)
        run.gpu_util_peak = round(max(util_peaks), 1)
    if mem_peaks:
        run.gpu_mem_peak_pct = round(max(mem_peaks), 1)
    return run


async def collect_runs(
    session: ClientSession,
    workspace: str,
    projects: list[str] | None,
    max_runs: int,
) -> list[RunMetrics]:
    """Sweep projects -> experiments -> per-run metrics, capped at max_runs."""
    if not projects:
        listing = await call_tool(session, "list_projects", {"workspace": workspace, "page_size": 100})
        projects = list(listing.get("projects", []))

    runs: list[RunMetrics] = []
    for project in projects:
        if len(runs) >= max_runs:
            break
        experiments = await call_tool(
            session,
            "list_experiments",
            {"workspace": workspace, "project_name": project, "page_size": 100},
        )
        for exp in experiments.get("experiments", []):
            if len(runs) >= max_runs:
                break
            runs.append(await fetch_run(session, workspace, project, exp["id"]))
    return runs
