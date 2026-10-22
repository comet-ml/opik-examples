"""Every Opik SDK and REST call used by the eval-in-CI example lives here."""

# WHY: one access layer so the CLI and the pure compare core never touch the network, and tests
# swap in stub clients.

import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import opik
from opik import url_helpers
from opik.config import OPIK_WORKSPACE_DEFAULT_NAME
from opik.rest_api.types.dataset_item_compare import DatasetItemCompare
from opik.rest_api.types.experiment_public import ExperimentPublic

_BASELINE_PAGE = 20


class ConfigError(RuntimeError):
    """Raised for setup problems the user can fix (env vars, refs, names)."""


@dataclass(frozen=True)
class GitContext:
    branch: str
    sha7: str
    pr_number: str | None
    actor: str | None


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def git_context(pr_override: str | None = None) -> GitContext:
    """Resolve branch, short sha, PR number and actor from CI env or git."""
    ref_name = os.environ.get("GITHUB_REF_NAME") or None
    branch = (
        os.environ.get("GITHUB_HEAD_REF") or ref_name or _git("rev-parse", "--abbrev-ref", "HEAD") or "local"
    )
    # WHY: on pull_request events GITHUB_SHA is the merge commit, so the workflow passes the head sha.
    sha = os.environ.get("OPIK_EVAL_GIT_SHA") or os.environ.get("GITHUB_SHA")
    sha7 = sha[:7] if sha else (_git("rev-parse", "--short=7", "HEAD") or "nogit")

    pr_number = pr_override
    if pr_number is None and ref_name and ref_name.endswith("/merge"):
        candidate = ref_name[: -len("/merge")]
        if candidate.isdigit():
            pr_number = candidate

    return GitContext(
        branch=branch,
        sha7=sha7,
        pr_number=pr_number,
        actor=os.environ.get("GITHUB_ACTOR") or None,
    )


def experiment_name(ctx: GitContext) -> str:
    return f"{ctx.branch.replace('/', '-')}-{ctx.sha7}"


def make_client() -> opik.Opik:
    """Build an Opik client and probe it; raise ConfigError with setup help."""
    try:
        client = opik.Opik()
        client.rest_client.check.get_workspace_name()
    except Exception as exc:
        raise ConfigError(
            "Could not connect to Opik. Set OPIK_API_KEY, OPIK_WORKSPACE and, "
            "for a custom host, OPIK_URL_OVERRIDE (value shape "
            f"https://<host>/opik/api). Original error: {exc}"
        ) from exc
    return client


def server_version(client: opik.Opik) -> str | None:
    try:
        info = client.rest_client.version()
    except Exception:
        return None
    if isinstance(info, dict) and info.get("version"):
        return str(info["version"])
    return str(info)


def ui_base_and_workspace(client: opik.Opik) -> tuple[str, str]:
    """Return the UI base URL (trailing slash) and the real workspace name."""
    base = url_helpers.get_base_url(client.config.url_override)
    workspace = client.config.workspace
    if workspace == OPIK_WORKSPACE_DEFAULT_NAME:
        workspace = client.rest_client.check.get_workspace_name().workspace_name
    return base, workspace


# WHY: the backend tag filter is a substring match and runs carry the branch tag too; match exactly.
def find_baseline(
    client: Any,
    dataset_id: str,
    *,
    tag: str = "baseline",
    exclude_id: str | None = None,
) -> ExperimentPublic | None:
    """Newest experiment on the dataset with the exact tag, skipping exclude_id."""
    # WHY: candidate runs whose branch tag contains the word push the baseline past page one.
    page = 1
    while True:
        resp = client.rest_client.experiments.find_experiments(
            dataset_id=dataset_id,
            filters=json.dumps([{"field": "tags", "operator": "contains", "value": tag}]),
            sorting=json.dumps([{"field": "created_at", "direction": "DESC"}]),
            page=page,
            size=_BASELINE_PAGE,
        )
        content = list(resp.content or [])
        for exp in content:
            if exp.id != exclude_id and tag in (exp.tags or []):
                return exp
        if len(content) < _BASELINE_PAGE:
            return None
        page += 1


# WHY: tag only after success, since evaluate() registers the experiment before the items run.
def mark_baseline(client: Any, experiment_id: str, tag: str = "baseline") -> None:
    """Add the baseline tag once the run has finished successfully."""
    client.rest_client.experiments.update_experiment(id=experiment_id, tags_to_add=[tag])


def resolve_experiment(client: Any, name_or_id: str, project_name: str | None) -> ExperimentPublic:
    """Resolve an experiment by id first, then by exact name (newest wins)."""
    try:
        return client.rest_client.experiments.get_experiment_by_id(name_or_id)
    except Exception:
        pass
    exact: list[Any] = []
    last_error: Exception | None = None
    # WHY: project_name is only a hint (experiments live under the dataset's project); retry without it.
    for hint in [project_name, None] if project_name else [None]:
        try:
            candidates = client.get_experiments_by_name(name_or_id, project_name=hint)
        except Exception as exc:
            last_error = exc
            continue
        exact = [e for e in candidates if e.name == name_or_id]
        if exact:
            break
    if not exact:
        detail = f": {last_error}" if last_error else ""
        raise ConfigError(f"No experiment with exact name '{name_or_id}' found{detail}")
    datas = [e.get_experiment_data() for e in exact]
    return max(datas, key=lambda d: d.created_at)  # type: ignore[no-any-return]


def fetch_compare_rows(
    client: Any,
    dataset_id: str,
    experiment_ids: Sequence[str],
    page_size: int = 100,
) -> list[DatasetItemCompare]:
    """Page through dataset items with their experiment items for the ids."""
    rows: list[Any] = []
    page = 1
    while True:
        resp = client.rest_client.datasets.find_dataset_items_with_experiment_items(
            id=dataset_id,
            experiment_ids=json.dumps(list(experiment_ids)),
            page=page,
            size=page_size,
            truncate=True,
        )
        content = list(resp.content or [])
        rows.extend(content)
        total = getattr(resp, "total", None)
        if len(content) < page_size:
            break
        if total is not None and page * page_size >= total:
            break
        page += 1
    return rows


def trace_url_builder(ui_base: str, workspace: str, project_id: str | None) -> Callable[[str], str | None]:
    """Return trace_id -> UI URL, or None when the project id is unknown."""

    def build(trace_id: str) -> str | None:
        if not project_id:
            return None
        return f"{ui_base}opik/{workspace}/projects/{project_id}/traces?trace={trace_id}"

    return build


def load_callable(ref: str) -> Callable[..., Any]:
    """Load 'module:attr' with the current directory importable."""
    module_name, sep, attr = ref.rpartition(":")
    if not sep or not module_name or not attr:
        raise ConfigError(f"Bad callable reference '{ref}': expected module:attr.")
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ConfigError(f"Cannot import module for '{ref}': {exc}") from exc
    try:
        target = getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError(f"Module '{module_name}' has no attribute for '{ref}'.") from exc
    return target  # type: ignore[no-any-return]
