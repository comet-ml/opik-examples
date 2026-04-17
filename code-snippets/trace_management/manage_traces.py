#!/usr/bin/env python3
"""
Opik Trace Manager — inspect and delete traces by date range, tags, or TTL policies.

Workflow:
  1. List first   →  python manage_traces.py list  [filter flags]
  2. Dry-run      →  python manage_traces.py delete [filter flags] --dry-run
  3. Execute      →  python manage_traces.py delete [filter flags] --yes

Requires environment variables:
  OPIK_API_KEY      Opik / Comet API key
  OPIK_WORKSPACE    Workspace name
  OPIK_BASE_URL     Base URL (default: https://www.comet.com)
"""

import argparse
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://www.comet.com"
BATCH_SIZE = 1000        # Traces fetched per list page
DELETE_BATCH_SIZE = 200  # Traces per delete request (smaller = more reliable)
RATE_LIMIT_DELAY = 0.2   # Seconds between batch deletes

# ---------------------------------------------------------------------------
# 2. Config / Auth
# ---------------------------------------------------------------------------


def get_env() -> dict:
    api_key = os.environ.get("OPIK_API_KEY")
    workspace = os.environ.get("OPIK_WORKSPACE")
    base_url = os.environ.get("OPIK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    if not api_key:
        _die("OPIK_API_KEY environment variable is not set.")
    if not workspace:
        _die("OPIK_WORKSPACE environment variable is not set.")

    return {"api_key": api_key, "workspace": workspace, "base_url": base_url}


def _make_headers(env: dict) -> dict:
    return {
        "Authorization": f"Bearer {env['api_key']}",
        "Comet-Workspace": env["workspace"],
        "Content-Type": "application/json",
    }


def load_config(path: str) -> dict:
    """Load and validate a JSON config file. Exits on any error."""
    try:
        with open(path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        _die(f"Cannot read config file: {path}")
    except json.JSONDecodeError as e:
        _die(f"Config file is not valid JSON: {e}")

    # projects must be a list if present
    if "projects" in cfg and not isinstance(cfg["projects"], list):
        _die('"projects" must be a list of strings.')

    # warn if both filters and ttl_rules are present
    has_filters = "filters" in cfg and cfg["filters"]
    has_ttl = "ttl_rules" in cfg and cfg["ttl_rules"]
    if has_filters and has_ttl:
        print('WARNING: both "filters" and "ttl_rules" found — "ttl_rules" takes precedence.')

    # validate ttl_rules entries
    for i, rule in enumerate(cfg.get("ttl_rules", [])):
        if "older_than_days" not in rule:
            _die(f'ttl_rules[{i}] is missing required field "older_than_days".')
        days = rule["older_than_days"]
        if not isinstance(days, int) or days <= 0:
            _die(f'ttl_rules[{i}].older_than_days must be a positive integer, got: {days!r}')
        if not isinstance(rule.get("tags", []), list):
            _die(f'ttl_rules[{i}].tags must be a list of strings.')
        if not isinstance(rule.get("exclude_tags", []), list):
            _die(f'ttl_rules[{i}].exclude_tags must be a list of strings.')

    # validate flat filters block
    f = cfg.get("filters", {}) or {}
    if f.get("older_than_days") and f.get("before"):
        _die('"filters" cannot have both "older_than_days" and "before".')
    if f.get("older_than_days") is not None:
        d = f["older_than_days"]
        if not isinstance(d, int) or d <= 0:
            _die(f'"filters.older_than_days" must be a positive integer, got: {d!r}')

    return cfg


# ---------------------------------------------------------------------------
# 3. Filter Model
# ---------------------------------------------------------------------------


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    _die(f"Cannot parse date: {s!r}. Use ISO 8601 format, e.g. 2025-01-31 or 2025-01-31T12:00:00.")


@dataclasses.dataclass
class TraceFilter:
    """
    Composable trace filter. Add new filter types here:
      1. Add a field.
      2. Add the filter dict in to_api_params().
      3. Add the CLI flag in add_filter_args().
      4. Add the config key in from_config().
    """
    before: Optional[datetime] = None
    after:  Optional[datetime] = None
    tags:         dataclasses.field(default_factory=list) = dataclasses.field(default_factory=list)
    exclude_tags: dataclasses.field(default_factory=list) = dataclasses.field(default_factory=list)

    def to_api_params(self) -> dict:
        """Produce query params for GET /traces."""
        params: dict = {}
        api_filters: list[dict] = []

        if self.before is not None:
            # to_time is a dedicated param, not a filter object
            params["to_time"] = _fmt_dt(self.before)

        if self.after is not None:
            api_filters.append({"field": "start_time", "operator": ">", "value": _fmt_dt(self.after)})

        for tag in self.tags:
            api_filters.append({"field": "tags", "operator": "contains", "value": tag})

        for tag in self.exclude_tags:
            api_filters.append({"field": "tags", "operator": "not_contains", "value": tag})

        if api_filters:
            params["filters"] = json.dumps(api_filters)

        return params

    def describe(self) -> str:
        parts = []
        if self.before:
            parts.append(f"before {self.before.date()}")
        if self.after:
            parts.append(f"after {self.after.date()}")
        if self.tags:
            parts.append(f"tags: {self.tags}")
        if self.exclude_tags:
            parts.append(f"exclude tags: {self.exclude_tags}")
        return " | ".join(parts) if parts else "(no filters)"

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "TraceFilter":
        before = None
        if getattr(args, "before", None):
            before = _parse_date(args.before)
        elif getattr(args, "older_than_days", None):
            before = datetime.now(tz=timezone.utc) - timedelta(days=args.older_than_days)
        after = _parse_date(args.after) if getattr(args, "after", None) else None
        return cls(
            before=before,
            after=after,
            tags=list(getattr(args, "tag", None) or []),
            exclude_tags=list(getattr(args, "exclude_tag", None) or []),
        )

    @classmethod
    def from_config_filters(cls, f: dict) -> "TraceFilter":
        before = None
        if f.get("older_than_days"):
            before = datetime.now(tz=timezone.utc) - timedelta(days=f["older_than_days"])
        elif f.get("before"):
            before = _parse_date(f["before"])
        after = _parse_date(f["after"]) if f.get("after") else None
        return cls(
            before=before,
            after=after,
            tags=list(f.get("tags") or []),
            exclude_tags=list(f.get("exclude_tags") or []),
        )

    def merge_from_args(self, args: argparse.Namespace) -> "TraceFilter":
        """Return a new filter with CLI args applied on top (CLI wins)."""
        result = dataclasses.replace(self)
        if getattr(args, "before", None):
            result.before = _parse_date(args.before)
        elif getattr(args, "older_than_days", None):
            result.before = datetime.now(tz=timezone.utc) - timedelta(days=args.older_than_days)
        if getattr(args, "after", None):
            result.after = _parse_date(args.after)
        if getattr(args, "tag", None):
            result.tags = list(args.tag)
        if getattr(args, "exclude_tag", None):
            result.exclude_tags = list(args.exclude_tag)
        return result

    def is_empty(self) -> bool:
        return self.before is None and self.after is None and not self.tags and not self.exclude_tags


def expand_ttl_rules(rules: list[dict]) -> list[tuple["TraceFilter", str]]:
    """
    Expand a ttl_rules list into (TraceFilter, label) pairs.

    Rules are sorted shortest-retention-first (most aggressive first).
    The catch-all rule (empty tags) automatically excludes all tags
    configured in prior rules, matching the original tag-based deletion logic.
    """
    sorted_rules = sorted(rules, key=lambda r: r["older_than_days"])
    configured_tags: list[str] = []
    result: list[tuple[TraceFilter, str]] = []

    for rule in sorted_rules:
        days = rule["older_than_days"]
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        rule_tags: list[str] = rule.get("tags", [])
        rule_exclude: list[str] = rule.get("exclude_tags", [])

        if rule_tags:
            for tag in rule_tags:
                tf = TraceFilter(
                    before=cutoff,
                    tags=[tag],
                    exclude_tags=list(rule_exclude),
                )
                label = f"tag={tag!r}, >{days}d old"
                result.append((tf, label))
            configured_tags.extend(rule_tags)
        else:
            # catch-all: exclude everything seen so far
            tf = TraceFilter(
                before=cutoff,
                exclude_tags=configured_tags + rule_exclude,
            )
            desc = rule.get("description", f"no configured tags, >{days}d old")
            result.append((tf, desc))

    return result


# ---------------------------------------------------------------------------
# 4. Project API
# ---------------------------------------------------------------------------


def get_all_projects(env: dict) -> list[dict]:
    """Return all projects in the workspace as list of {id, name} dicts."""
    url = f"{env['base_url']}/opik/api/v1/private/projects"
    projects: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            url,
            headers=_make_headers(env),
            params={"workspace_name": env["workspace"], "page": page, "size": 100},
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [])
        if not content:
            break
        projects.extend({"id": p["id"], "name": p["name"]} for p in content)
        if len(projects) >= data.get("total", 0):
            break
        page += 1
    return projects


def resolve_projects(env: dict, names: list[str]) -> list[dict]:
    """
    Validate and resolve project names to {id, name} dicts.
    If names is empty, returns all projects in the workspace.
    Exits with an error if any named project is not found.
    """
    all_projects = get_all_projects(env)
    index = {p["name"]: p for p in all_projects}

    if not names:
        if not all_projects:
            _die("No projects found in workspace.")
        print(f"  No projects specified — targeting all {len(all_projects)} workspace project(s).")
        return all_projects

    result: list[dict] = []
    missing: list[str] = []
    for name in names:
        if name in index:
            result.append(index[name])
        else:
            missing.append(name)

    if missing:
        _die(f"Project(s) not found in workspace: {missing}\nAvailable: {sorted(index.keys())}")

    return result


# ---------------------------------------------------------------------------
# 5. Trace API
# ---------------------------------------------------------------------------


def fetch_trace_count(env: dict, project_name: str, tf: TraceFilter) -> int:
    """Fast count-only query. Uses size=1 and reads the 'total' field."""
    url = f"{env['base_url']}/opik/api/v1/private/traces"
    params = {"project_name": project_name, "page": 1, "size": 1}
    params.update(tf.to_api_params())
    resp = requests.get(url, headers=_make_headers(env), params=params)
    resp.raise_for_status()
    return resp.json().get("total", 0)


def _fetch_trace_page(env: dict, project_name: str, tf: TraceFilter, page: int) -> dict:
    url = f"{env['base_url']}/opik/api/v1/private/traces"
    params = {"project_name": project_name, "page": page, "size": BATCH_SIZE}
    params.update(tf.to_api_params())
    resp = requests.get(url, headers=_make_headers(env), params=params)
    resp.raise_for_status()
    return resp.json()


def collect_trace_ids(
    env: dict,
    project_name: str,
    tf: TraceFilter,
    label: str = "",
) -> tuple[list[str], Optional[str]]:
    """Collect all matching trace IDs by always fetching page 1 until exhausted.

    We always request page=1 rather than incrementing the page number.
    Offset-based pagination against a live dataset is unreliable: after deleting
    the first N traces, page 2 of the original result set no longer exists at the
    same offset, causing traces to be skipped. Repeatedly fetching page 1 until
    the response is empty avoids this entirely.
    """
    all_ids: list[str] = []
    project_id: Optional[str] = None

    desc = f" ({label})" if label else ""
    print(f"  Collecting IDs{desc} ...", flush=True)

    # Get the expected total first for progress reporting
    data = _fetch_trace_page(env, project_name, tf, page=1)
    total = data.get("total", 0)
    content = data.get("content", [])

    if not content:
        return all_ids, project_id

    batch_num = 1
    while content:
        for trace in content:
            all_ids.append(trace["id"])
            if project_id is None:
                project_id = trace.get("project_id")

        print(f"    Batch {batch_num}: {len(content)} traces (collected: {len(all_ids)} / {total})")

        if len(content) < BATCH_SIZE:
            # Last page — no more results
            break

        batch_num += 1
        data = _fetch_trace_page(env, project_name, tf, page=1)
        total = data.get("total", 0)
        content = data.get("content", [])

    return all_ids, project_id


def batch_delete(
    env: dict,
    trace_ids: list[str],
    project_id: Optional[str],
    dry_run: bool,
) -> int:
    total_deleted = 0
    num_batches = (len(trace_ids) + DELETE_BATCH_SIZE - 1) // DELETE_BATCH_SIZE

    for i in range(0, len(trace_ids), DELETE_BATCH_SIZE):
        batch = trace_ids[i : i + DELETE_BATCH_SIZE]
        batch_num = i // DELETE_BATCH_SIZE + 1

        if dry_run:
            print(f"    [DRY RUN] Would delete {len(batch)} traces (batch {batch_num}/{num_batches})")
            total_deleted += len(batch)
            continue

        url = f"{env['base_url']}/opik/api/v1/private/traces/delete"
        payload: dict = {"ids": batch}
        if project_id:
            payload["project_id"] = project_id

        resp = requests.post(url, headers=_make_headers(env), json=payload)
        resp.raise_for_status()

        total_deleted += len(batch)
        print(f"    Deleted batch {batch_num}/{num_batches}: {len(batch)} traces (running total: {total_deleted})")

        if i + DELETE_BATCH_SIZE < len(trace_ids):
            time.sleep(RATE_LIMIT_DELAY)

    return total_deleted


# ---------------------------------------------------------------------------
# 6. Command Handlers
# ---------------------------------------------------------------------------


def cmd_list(env: dict, projects: list[dict], filters: list[tuple[TraceFilter, str]]) -> None:
    """Count-only inspection. No deletions."""
    print()
    grand_total = 0

    for project in projects:
        name = project["name"]
        project_total = 0

        for tf, label in filters:
            try:
                count = fetch_trace_count(env, name, tf)
            except requests.HTTPError as e:
                _http_err(f"listing traces for {name!r}", e)
                continue
            project_total += count

        matches = f"{project_total:,}"
        print(f"  {name:<40}  {matches:>8} traces match")
        grand_total += project_total

    print()
    print("  " + "─" * 55)
    print(f"  Total: {grand_total:,} traces across {len(projects)} project(s)")
    print()


def cmd_delete(
    env: dict,
    projects: list[dict],
    filters: list[tuple[TraceFilter, str]],
    dry_run: bool,
    yes: bool,
) -> None:
    """Delete (or dry-run) traces matching the filters across all projects."""
    if not dry_run and not yes:
        # Preview counts first, then ask
        print()
        print("  Calculating scope...")
        grand_preview = 0
        for project in projects:
            for tf, _ in filters:
                try:
                    grand_preview += fetch_trace_count(env, project["name"], tf)
                except requests.HTTPError as e:
                    _http_err(f"counting traces for {project['name']!r}", e)
        print(f"  {grand_preview:,} traces would be deleted across {len(projects)} project(s).")
        print()
        answer = input("  Delete? [y/N] ").strip().lower()
        if answer != "y":
            print("  Aborted.")
            return
        print()

    grand_total = 0

    for project in projects:
        name = project["name"]
        project_total = 0
        print(f"  {'='*58}")
        print(f"  Project: {name}")
        print(f"  {'='*58}")

        for tf, label in filters:
            try:
                ids, pid = collect_trace_ids(env, name, tf, label=label)
            except requests.HTTPError as e:
                _http_err(f"listing traces for {name!r}", e)
                continue

            if not ids:
                print(f"  No traces found ({label})")
                continue

            # Fallback: resolve project_id from the projects index if traces didn't include it
            if pid is None:
                pid = project.get("id")

            print(f"  Found {len(ids):,} traces ({label})")
            try:
                deleted = batch_delete(env, ids, pid, dry_run=dry_run)
                project_total += deleted
                verb = "would be deleted" if dry_run else "deleted"
                print(f"  Done: {deleted:,} traces {verb}")
            except requests.HTTPError as e:
                _http_err("deleting traces", e)
            print()

        print(f"  Project subtotal: {project_total:,} traces")
        print()
        grand_total += project_total

    verb = "would be deleted" if dry_run else "deleted"
    suffix = "\n  No changes were made." if dry_run else ""
    print(f"  {'='*58}")
    print(f"  Grand total: {grand_total:,} traces {verb} across {len(projects)} project(s).{suffix}")


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------


def add_filter_args(parser: argparse.ArgumentParser) -> None:
    """Add shared filter flags to a subparser."""
    g = parser.add_argument_group("filter options")
    g.add_argument("--projects", nargs="+", metavar="NAME",
                   help="Project names to target. Omit to target all workspace projects.")
    g.add_argument("--config", metavar="FILE",
                   help="JSON config file (projects, filters or ttl_rules). CLI flags override.")

    age = g.add_mutually_exclusive_group()
    age.add_argument("--older-than-days", type=int, metavar="N",
                     help="Target traces older than N days.")
    age.add_argument("--before", metavar="DATE",
                     help="Target traces before this ISO 8601 date (e.g. 2025-01-31).")

    g.add_argument("--after", metavar="DATE",
                   help="Target traces after this ISO 8601 date.")
    g.add_argument("--tag", nargs="+", metavar="TAG",
                   help="Include only traces containing ALL of these tags.")
    g.add_argument("--exclude-tag", nargs="+", metavar="TAG",
                   help="Exclude traces containing ANY of these tags.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage_traces.py",
        description="Inspect and delete Opik traces by date range, tags, or TTL policies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Workflow:\n"
            "  1. python manage_traces.py list  [filter flags]          # inspect counts\n"
            "  2. python manage_traces.py delete [filter flags] --dry-run  # preview\n"
            "  3. python manage_traces.py delete [filter flags] --yes      # execute\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("list", help="Count matching traces per project. No deletions.")
    add_filter_args(lp)

    dp = sub.add_parser("delete", help="Delete matching traces.")
    add_filter_args(dp)
    dp.add_argument("--dry-run", action="store_true",
                    help="Show what would be deleted without making any changes.")
    dp.add_argument("--yes", action="store_true",
                    help="Skip the confirmation prompt (for scripted/cron use).")

    return parser


def _resolve_filters(args: argparse.Namespace) -> tuple[list[str], list[tuple[TraceFilter, str]]]:
    """
    Merge config file (if any) with CLI flags.
    Returns (project_names, [(TraceFilter, label), ...]).
    CLI flags always override config values.
    """
    cfg: dict = {}
    if args.config:
        cfg = load_config(args.config)

    # Project names: CLI wins, then config, then empty (= all workspace)
    project_names: list[str] = list(getattr(args, "projects", None) or cfg.get("projects") or [])

    # Determine filter mode
    has_ttl = bool(cfg.get("ttl_rules"))
    has_cfg_filters = bool(cfg.get("filters"))

    if has_ttl:
        ttl_filters = expand_ttl_rules(cfg["ttl_rules"])
        # Apply any CLI overrides on top of each rule's filter
        merged = [(tf.merge_from_args(args), label) for tf, label in ttl_filters]
        return project_names, merged

    # Flat filters mode
    base_tf = TraceFilter()
    if has_cfg_filters:
        base_tf = TraceFilter.from_config_filters(cfg["filters"])

    final_tf = base_tf.merge_from_args(args)

    if final_tf.is_empty():
        _die(
            "No filter criteria specified.\n"
            "Use --older-than-days, --before, --after, --tag, --exclude-tag, or a --config file."
        )

    return project_names, [(final_tf, final_tf.describe())]


def _print_header(env: dict, cmd: str, projects: list[dict], filters: list[tuple[TraceFilter, str]], dry_run: bool = False) -> None:
    mode = "[DRY RUN] " if dry_run else ""
    action = "Inspector" if cmd == "list" else "Deletion"
    print(f"{mode}Opik Trace {action}")
    print(f"  Workspace : {env['workspace']}")
    print(f"  Base URL  : {env['base_url']}")
    print(f"  Projects  : {', '.join(p['name'] for p in projects)}")
    if len(filters) == 1:
        print(f"  Filters   : {filters[0][1]}")
    else:
        print(f"  Filters   : {len(filters)} TTL rule(s)")
        for tf, label in filters:
            print(f"              {label}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate config before touching the network or requiring env vars
    project_names, filters = _resolve_filters(args)

    env = get_env()

    print(f"Resolving projects...", flush=True)
    projects = resolve_projects(env, project_names)

    _print_header(env, args.cmd, projects, filters, dry_run=getattr(args, "dry_run", False))

    if args.cmd == "list":
        cmd_list(env, projects, filters)
    elif args.cmd == "delete":
        cmd_delete(env, projects, filters, dry_run=args.dry_run, yes=args.yes)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _http_err(context: str, exc: requests.HTTPError) -> None:
    print(f"  ERROR {context}: {exc}")
    if exc.response is not None:
        print(f"  Response: {exc.response.text}")


if __name__ == "__main__":
    main()
