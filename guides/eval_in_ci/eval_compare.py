"""Pure compare, policy and digest logic for eval-in-CI."""

# WHY: no network calls and no opik imports here; callers hand in REST rows, so the module is
# testable without Opik.

import json
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from composite_metric import DEFAULT_PASS_NAME, failing_metrics_from_reason

MARKER = "<!-- opik-eval -->"
_UNSCORED = "unscored"
_NO_REASON = "failed (no reason)"
_NOT_BELOW = "not_below_baseline"
_POLICY_FILES = ("opik-release-policy.yaml", ".opik/opik-release-policy.yaml")
_POLICY_KEYS = frozenset(
    {
        "min_items",
        "max_regressions",
        "pass_rate",
        "safety_tags",
        "subgroup_key",
        "latency_p90_max_increase",
        "cost_per_item_max_increase",
        "flaky_policy",
        "judge_validated",
    }
)


@dataclass(frozen=True)
class RunScore:
    name: str
    value: float
    reason: str | None


@dataclass(frozen=True)
class ItemRun:
    experiment_id: str
    dataset_item_id: str
    trace_id: str | None
    label: str | None
    scores: tuple[RunScore, ...]


@dataclass(frozen=True)
class ItemOutcome:
    dataset_item_id: str
    label: str | None
    baseline_passed: bool | None
    candidate_passed: bool | None
    baseline_pass_runs: int
    baseline_runs: int
    candidate_pass_runs: int
    candidate_runs: int
    failing_metrics: tuple[str, ...]
    worst_trace_id: str | None


@dataclass
class Comparison:
    baseline_id: str | None
    candidate_id: str
    items_scored: int
    pass_rate_baseline: float | None
    pass_rate_candidate: float
    newly_failing: list[ItemOutcome] = field(default_factory=list)
    newly_passing: list[ItemOutcome] = field(default_factory=list)
    still_failing: list[ItemOutcome] = field(default_factory=list)
    new_items: list[ItemOutcome] = field(default_factory=list)
    flaky: list[ItemOutcome] = field(default_factory=list)
    metric_means: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    pass_rule: str = ""


def rows_to_item_runs(rows: Iterable[Any], label_key: str = "scenario_id") -> list[ItemRun]:
    """Flatten DatasetItemCompare-shaped rows into one ItemRun per experiment item."""
    runs: list[ItemRun] = []
    for row in rows:
        data = getattr(row, "data", None)
        raw_label = data.get(label_key) if isinstance(data, dict) else None
        label = None if raw_label is None else str(raw_label)
        for item in getattr(row, "experiment_items", None) or []:
            scores = tuple(RunScore(s.name, float(s.value), s.reason) for s in (item.feedback_scores or []))
            runs.append(
                ItemRun(
                    experiment_id=item.experiment_id,
                    dataset_item_id=item.dataset_item_id,
                    trace_id=item.trace_id,
                    label=label,
                    scores=scores,
                )
            )
    return runs


def _pass_value(run: ItemRun, pass_name: str) -> float | None:
    for s in run.scores:
        if s.name == pass_name:
            return s.value
    return None


def _run_passed(run: ItemRun, pass_name: str) -> bool:
    value = _pass_value(run, pass_name)
    return value is not None and value >= 1.0


def _worst_run(runs: Sequence[ItemRun], pass_name: str) -> ItemRun:
    """Run with the lowest pass score; a run without the score is the worst."""

    def key(run: ItemRun) -> float:
        value = _pass_value(run, pass_name)
        return float("-inf") if value is None else value

    return min(runs, key=key)


def _failing_metrics(run: ItemRun, pass_name: str) -> tuple[str, ...]:
    for s in run.scores:
        if s.name == pass_name:
            return failing_metrics_from_reason(s.reason)
    return (_UNSCORED,)


def _means(runs: Iterable[ItemRun]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for run in runs:
        for s in run.scores:
            values.setdefault(s.name, []).append(s.value)
    return {name: sum(v) / len(v) for name, v in values.items()}


# WHY: an item with 0 < pass_runs < runs in either experiment is flaky and excluded from newly
# failing/passing by default, mirroring opik-verify's `flaky_policy: exclude`,
# so judge noise does not count as a regression or a fix. Items with no
# candidate runs are never new or flipped; with no baseline, failing items go to still_failing only.
def classify(
    runs: Sequence[ItemRun],
    *,
    baseline_id: str | None,
    candidate_id: str,
    pass_name: str = DEFAULT_PASS_NAME,
    pass_threshold: int | None = None,
) -> Comparison:
    """Compare candidate against baseline per dataset item."""
    grouped: dict[tuple[str, str], list[ItemRun]] = {}
    order: list[str] = []
    for run in runs:
        if run.dataset_item_id not in order:
            order.append(run.dataset_item_id)
        grouped.setdefault((run.dataset_item_id, run.experiment_id), []).append(run)

    def passes(n_pass: int, n_runs: int) -> bool | None:
        if n_runs == 0:
            return None
        return n_pass >= (n_runs if pass_threshold is None else pass_threshold)

    cmp = Comparison(
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        items_scored=0,
        pass_rate_baseline=None,
        pass_rate_candidate=0.0,
    )
    base_scored = base_passed = cand_scored = cand_passed = 0
    trial_counts: Counter[int] = Counter()

    for item_id in order:
        b_runs = grouped.get((item_id, baseline_id), []) if baseline_id else []
        c_runs = grouped.get((item_id, candidate_id), [])
        b_pass = sum(_run_passed(r, pass_name) for r in b_runs)
        c_pass = sum(_run_passed(r, pass_name) for r in c_runs)
        b_ok = passes(b_pass, len(b_runs))
        c_ok = passes(c_pass, len(c_runs))
        if b_runs:
            base_scored += 1
            base_passed += bool(b_ok)
        if c_runs:
            cand_scored += 1
            cand_passed += bool(c_ok)
            trial_counts[len(c_runs)] += 1

        worst = _worst_run(c_runs, pass_name) if c_runs else None
        failing: tuple[str, ...] = ()
        if worst is not None and not c_ok:
            failing = _failing_metrics(worst, pass_name)
        label = next((r.label for r in (c_runs or b_runs) if r.label), None)
        outcome = ItemOutcome(
            dataset_item_id=item_id,
            label=label,
            baseline_passed=b_ok,
            candidate_passed=c_ok,
            baseline_pass_runs=b_pass,
            baseline_runs=len(b_runs),
            candidate_pass_runs=c_pass,
            candidate_runs=len(c_runs),
            failing_metrics=failing,
            worst_trace_id=worst.trace_id if worst else None,
        )

        if baseline_id is not None and not c_runs:
            if b_ok is False:
                cmp.still_failing.append(outcome)
        elif baseline_id is not None and not b_runs:
            cmp.new_items.append(outcome)
        elif 0 < c_pass < len(c_runs) or 0 < b_pass < len(b_runs):
            cmp.flaky.append(outcome)
        elif baseline_id is None:
            if not c_ok:
                cmp.still_failing.append(outcome)
        elif b_ok and not c_ok:
            cmp.newly_failing.append(outcome)
        elif c_ok and not b_ok:
            cmp.newly_passing.append(outcome)
        elif not c_ok and not b_ok:
            cmp.still_failing.append(outcome)

    cmp.items_scored = cand_scored
    cmp.pass_rate_candidate = cand_passed / cand_scored if cand_scored else 0.0
    if baseline_id is not None:
        cmp.pass_rate_baseline = base_passed / base_scored if base_scored else 0.0

    base_means = _means(r for r in runs if baseline_id and r.experiment_id == baseline_id)
    cand_means = _means(r for r in runs if r.experiment_id == candidate_id)
    for name in [*base_means, *(n for n in cand_means if n not in base_means)]:
        cmp.metric_means[name] = (base_means.get(name), cand_means.get(name))

    n_trials = trial_counts.most_common(1)[0][0] if trial_counts else 0
    if pass_threshold is None:
        cmp.pass_rule = f"all {n_trials} trials"
    else:
        cmp.pass_rule = f"{pass_threshold} of {n_trials} trials (differs from UI)"
    return cmp


@dataclass(frozen=True)
class Policy:
    min_items: int = 10
    max_regressions: int = 0
    pass_rate: str | float = _NOT_BELOW
    flaky_policy: str = "exclude"


class PolicyError(ValueError):
    pass


def load_policy(path: Path | None) -> tuple[Policy, str]:
    """Load the release policy; return it with its source label."""
    if path is None:
        found = next((Path(p) for p in _POLICY_FILES if Path(p).is_file()), None)
        if found is None:
            return Policy(), "defaults"
        path = found
    elif not path.is_file():
        raise PolicyError(f"policy file not found: {path}")
    try:
        import yaml
    except ImportError as exc:
        raise PolicyError("pip install pyyaml") from exc
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise PolicyError(f"invalid policy file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyError(f"policy file {path} must be a mapping")
    for key in raw:
        if key not in _POLICY_KEYS:
            raise PolicyError(f"unknown policy key: {key}")

    defaults = Policy()
    pass_rate = raw.get("pass_rate", defaults.pass_rate)
    if isinstance(pass_rate, bool) or not (
        pass_rate == _NOT_BELOW or (isinstance(pass_rate, int | float) and 0 <= pass_rate <= 1)
    ):
        raise PolicyError(f"pass_rate must be '{_NOT_BELOW}' or a number in 0..1")
    flaky_policy = raw.get("flaky_policy", defaults.flaky_policy)
    if flaky_policy not in ("exclude", "count"):
        raise PolicyError("flaky_policy must be 'exclude' or 'count'")
    for key in ("min_items", "max_regressions"):
        value = raw.get(key, getattr(defaults, key))
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PolicyError(f"{key} must be a non-negative integer")
    return (
        Policy(
            min_items=raw.get("min_items", defaults.min_items),
            max_regressions=raw.get("max_regressions", defaults.max_regressions),
            pass_rate=pass_rate,
            flaky_policy=flaky_policy,
        ),
        f"file:{path}",
    )


@dataclass(frozen=True)
class Criterion:
    name: str
    threshold: str
    observed: str
    passed: bool


@dataclass(frozen=True)
class PolicyVerdict:
    passed: bool
    criteria: list[Criterion]
    status: str


def evaluate_policy(cmp: Comparison, policy: Policy, *, mark_baseline: bool = False) -> PolicyVerdict:
    """Apply the policy; hold beats insufficient_evidence."""
    has_baseline = cmp.baseline_id is not None
    regressions = len(cmp.newly_failing)
    if policy.flaky_policy == "count":
        regressions += sum(1 for o in cmp.flaky if o.baseline_passed and not o.candidate_passed)

    criteria = [
        Criterion(
            "min_items",
            f">= {policy.min_items}",
            str(cmp.items_scored),
            cmp.items_scored >= policy.min_items,
        )
    ]
    if has_baseline:
        criteria.append(
            Criterion(
                "max_regressions",
                f"<= {policy.max_regressions}",
                str(regressions),
                regressions <= policy.max_regressions,
            )
        )
        cand = cmp.pass_rate_candidate
        if policy.pass_rate == _NOT_BELOW:
            base = cmp.pass_rate_baseline or 0.0
            rate_ok = cand >= base - 1e-9
            threshold = f">= baseline ({base:.2f})"
        else:
            rate_ok = cand >= float(policy.pass_rate) - 1e-9
            threshold = f">= {float(policy.pass_rate):.2f}"
        criteria.append(Criterion("pass_rate", threshold, f"{cand:.2f}", rate_ok))
    else:
        criteria.append(Criterion("max_regressions", f"<= {policy.max_regressions}", "n/a", True))
        criteria.append(Criterion("pass_rate", str(policy.pass_rate), "n/a", True))
    criteria.append(Criterion("flaky_policy", policy.flaky_policy, str(len(cmp.flaky)), True))

    by_name = {c.name: c for c in criteria}
    if not has_baseline:
        status = "baseline_created" if mark_baseline else "no_baseline"
    elif not by_name["max_regressions"].passed or not by_name["pass_rate"].passed:
        status = "hold"
    elif not by_name["min_items"].passed:
        status = "insufficient_evidence"
    else:
        status = "ok"
    passed = status in ("ok", "baseline_created", "no_baseline")
    return PolicyVerdict(passed=passed, criteria=criteria, status=status)


@dataclass(frozen=True)
class DigestMeta:
    baseline_name: str | None
    candidate_name: str
    compare_url: str | None
    trace_url: Callable[[str], str | None]
    policy_source: str
    server_version: str | None
    git: dict[str, str]
    mark_baseline: bool | None = None


def _baseline_line(cmp: Comparison, meta: DigestMeta) -> str:
    if cmp.baseline_id is not None:
        return f"Baseline: {meta.baseline_name} ({cmp.baseline_id})"
    if meta.mark_baseline:
        return f"Baseline: this run ({meta.candidate_name})"
    return "Baseline: none found - merge to main with --mark-baseline to create one"


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _delta(base: float | None, cand: float | None) -> float | None:
    return None if base is None or cand is None else cand - base


def _row(o: ItemOutcome, meta: DigestMeta, indent: str = "") -> str:
    name = o.label or o.dataset_item_id
    link = meta.trace_url(o.worst_trace_id) if o.worst_trace_id else None
    suffix = f" ([trace]({link}))" if link else ""
    if o.candidate_passed:
        detail = "passed"
    else:
        detail = ", ".join(o.failing_metrics) or _NO_REASON
    return f"{indent}- {name}: {detail}{suffix}"


def _section(title: str, outcomes: list[ItemOutcome], meta: DigestMeta, max_rows: int) -> list[str]:
    lines = ["", f"### {title}", ""]
    if not outcomes:
        return [*lines, "none"]
    lines.extend(_row(o, meta) for o in outcomes[:max_rows])
    if len(outcomes) > max_rows:
        lines.append(f"+{len(outcomes) - max_rows} more")
    return lines


def _still_failing_section(outcomes: list[ItemOutcome], meta: DigestMeta, max_rows: int) -> list[str]:
    lines = ["", "### Still failing", ""]
    if not outcomes:
        return [*lines, "none"]
    groups: dict[str, list[ItemOutcome]] = {}
    for o in outcomes:
        for metric in o.failing_metrics or (_NO_REASON,):
            groups.setdefault(metric, []).append(o)
    total = sum(len(v) for v in groups.values())
    shown = 0
    for metric, members in groups.items():
        if shown >= max_rows:
            break
        lines.append(f"- **{metric}**")
        for o in members[: max_rows - shown]:
            link = meta.trace_url(o.worst_trace_id) if o.worst_trace_id else None
            suffix = f" ([trace]({link}))" if link else ""
            lines.append(f"  - {o.label or o.dataset_item_id}{suffix}")
            shown += 1
    if total > shown:
        lines.append(f"+{total - shown} more")
    return lines


def render_markdown(cmp: Comparison, verdict: PolicyVerdict, meta: DigestMeta, max_rows: int = 25) -> str:
    failed = [c.name for c in verdict.criteria if not c.passed]
    verdict_line = f"**Verdict:** {verdict.status}"
    if failed:
        verdict_line += f" - failed: {', '.join(failed)}"
    delta = _delta(cmp.pass_rate_baseline, cmp.pass_rate_candidate)
    rate = f"Pass rate: {_fmt(cmp.pass_rate_baseline)} -> {_fmt(cmp.pass_rate_candidate)}"
    if delta is not None:
        rate += f" ({delta:+.2f})"

    lines = [
        MARKER,
        f"## Opik eval: {meta.candidate_name}",
        "",
        _baseline_line(cmp, meta),
        "",
        verdict_line,
        "",
        rate,
        f"Items scored: {cmp.items_scored} | Pass rule: {cmp.pass_rule}",
    ]
    lines += _section("Newly failing", cmp.newly_failing, meta, max_rows)
    lines += _section("Newly passing", cmp.newly_passing, meta, max_rows)
    lines += _still_failing_section(cmp.still_failing, meta, max_rows)
    lines += _section("Flaky", cmp.flaky, meta, max_rows)
    lines += _section("New items", cmp.new_items, meta, max_rows)
    lines += [
        "",
        "### Per-metric means",
        "",
        "| metric | baseline | candidate | delta |",
        "|---|---|---|---|",
    ]
    for name, (base, cand) in cmp.metric_means.items():
        d = _delta(base, cand)
        lines.append(f"| {name} | {_fmt(base)} | {_fmt(cand)} | {'n/a' if d is None else f'{d:+.2f}'} |")
    lines += ["", "### Compare", ""]
    lines.append(f"[Open in Opik]({meta.compare_url})" if meta.compare_url else "none")
    return "\n".join(lines) + "\n"


def render_json(cmp: Comparison, verdict: PolicyVerdict, meta: DigestMeta) -> dict[str, Any]:
    delta = _delta(cmp.pass_rate_baseline, cmp.pass_rate_candidate)
    failed = [c.name for c in verdict.criteria if not c.passed]
    return {
        "status": verdict.status,
        "verdict": {"passed": verdict.passed, "failed_criteria": failed},
        "pass_rate": {
            "baseline": cmp.pass_rate_baseline,
            "candidate": cmp.pass_rate_candidate,
            "delta": delta,
        },
        "pass_rule": cmp.pass_rule,
        "items_scored": cmp.items_scored,
        "newly_failing": [asdict(o) for o in cmp.newly_failing],
        "newly_passing": [asdict(o) for o in cmp.newly_passing],
        "still_failing": [asdict(o) for o in cmp.still_failing],
        "new_items": [asdict(o) for o in cmp.new_items],
        "flaky": [asdict(o) for o in cmp.flaky],
        "metric_means": {name: {"baseline": b, "candidate": c} for name, (b, c) in cmp.metric_means.items()},
        "criteria": [asdict(c) for c in verdict.criteria],
        "compare_url": meta.compare_url,
        "meta": {
            "baseline_name": meta.baseline_name,
            "candidate_name": meta.candidate_name,
            "policy_source": meta.policy_source,
            "server_version": meta.server_version,
            "git": dict(meta.git),
        },
    }


def compare_url(ui_base: str, workspace: str, dataset_id: str, experiment_ids: Sequence[str]) -> str:
    ids = quote(json.dumps(list(experiment_ids)))
    return f"{ui_base}opik/{workspace}/experiments/{dataset_id}/compare?experiments={ids}"
