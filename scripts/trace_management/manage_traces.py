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

Exit codes:
  0  success
  1  any failure — bad config, or an API error during listing/deleting.
     Safe to alert on from cron.
"""

import argparse
import dataclasses
import json
import os
import sys
from datetime import UTC, datetime, timedelta

import opik
from opik.api_objects import rest_helpers, rest_stream_parser
from opik.rest_api.core.api_error import ApiError
from opik.rest_api.types import trace_public
from opik.rest_api.types.trace_filter_public import TraceFilterPublic

# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://www.comet.com"
DEFAULT_TIME_FIELD = "ingestion"  # See TraceFilter.time_field for why this, not start_time.
SEARCH_PAGE_SIZE = 1000  # Traces read per search page
DELETE_BATCH_SIZE = 200  # Ids per delete call (API hard cap is 1000)

# WHY: we only ever need `id` (to delete) and `start_time` (to show the operator
# what the cutoff caught). Everything below is dropped server-side so we don't
# transfer trace bodies — potentially gigabytes — just to collect a list of UUIDs.
# `strip_attachments` additionally stops the backend downloading and reinjecting
# attachment blobs into a response we discard.
EXCLUDE_FIELDS = [
    "input",
    "output",
    "metadata",
    "feedback_scores",
    "span_feedback_scores",
    "comments",
    "guardrails_validations",
    "usage",
    "total_estimated_cost",
    "span_count",
    "llm_span_count",
    "has_tool_spans",
    "providers",
    "experiment",
    "error_info",
]

# Set by _fail() whenever a recoverable error is reported, so main() can exit non-zero.
_FAILED = False

# ---------------------------------------------------------------------------
# 2. Config / Auth
# ---------------------------------------------------------------------------


def get_client() -> tuple[opik.Opik, dict]:
    """Build an Opik client from the documented env vars."""
    api_key = os.environ.get("OPIK_API_KEY")
    workspace = os.environ.get("OPIK_WORKSPACE")
    base_url = os.environ.get("OPIK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    if not api_key:
        _die("OPIK_API_KEY environment variable is not set.")
    if not workspace:
        _die("OPIK_WORKSPACE environment variable is not set.")

    # The SDK wants the API root; the documented env var is the site root.
    client = opik.Opik(
        api_key=api_key,
        workspace=workspace,
        host=f"{base_url}/opik/api/",
        _show_misconfiguration_message=False,
    )
    return client, {"workspace": workspace, "base_url": base_url}


def load_config(path: str) -> dict:
    """Load and validate a JSON config file. Exits on any error."""
    try:
        with open(path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        _die(f"Cannot read config file: {path}")
    except json.JSONDecodeError as e:
        _die(f"Config file is not valid JSON: {e}")

    if "projects" in cfg and not isinstance(cfg["projects"], list):
        _die('"projects" must be a list of strings.')

    has_filters = "filters" in cfg and cfg["filters"]
    has_ttl = "ttl_rules" in cfg and cfg["ttl_rules"]
    if has_filters and has_ttl:
        print('WARNING: both "filters" and "ttl_rules" found — "ttl_rules" takes precedence.')

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

    for where, block in [("", cfg), ("filters.", cfg.get("filters") or {})]:
        tfield = block.get("time_field")
        if tfield is not None and tfield not in ("start_time", "ingestion"):
            _die(f'"{where}time_field" must be "start_time" or "ingestion", got: {tfield!r}')

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
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    _die(f"Cannot parse date: {s!r}. Use ISO 8601 format, e.g. 2025-01-31 or 2025-01-31T12:00:00.")


@dataclasses.dataclass
class TraceFilter:
    """
    Composable trace filter. Add new filter types here:
      1. Add a field.
      2. Add it to to_api_kwargs() (dates) or to_sdk_filters() (everything else).
      3. Add the CLI flag in add_filter_args().
      4. Add the config key in from_config_filters().
    """

    before: datetime | None = None
    after: datetime | None = None
    tags: list[str] = dataclasses.field(default_factory=list)
    exclude_tags: list[str] = dataclasses.field(default_factory=list)

    # Which clock the date bounds are measured on.
    #
    #   "ingestion"  — the timestamp embedded in the trace id (UUIDv7), i.e. when the
    #     backend received the trace. Assigned server-side, so a client cannot
    #     influence it; also lets the backend prune partitions, which is cheaper on
    #     very large projects. This is the default, and the answer to "how long have
    #     we held this data".
    #   "start_time" — the trace's own timestamp, and the one shown in the Opik UI.
    #     Answers "how old is the activity this trace describes".
    #
    # Default is "ingestion" because the usual reason to delete traces on a schedule is
    # a retention commitment — "we do not keep customer data longer than 90 days" — and
    # that is a claim about custody, measured from when we received it.
    #
    # It also matters that start_time is supplied by whatever wrote the trace, and is
    # accepted as given. A retention control keyed on a field the data producer sets is
    # not a control: a skewed clock or a bad actor stamping start_time far in the future
    # keeps data past its deletion date, and the sweep still reports success. Ingestion
    # time cannot be shifted that way.
    #
    # For traces logged as the work happens the two clocks agree to within milliseconds.
    # They diverge for backfilled or replayed data — a trace imported today carrying
    # last year's start_time is old on one clock and seconds old on the other. Under
    # "ingestion" such a trace is correctly retained (we have held it for seconds);
    # choose "start_time" when the policy is really about the age of the activity.
    time_field: str = DEFAULT_TIME_FIELD

    def to_api_kwargs(self) -> dict:
        """Date bounds expressed as dedicated params — the ingestion clock only.

        `to_time` / `from_time` bound the trace id, so they are meaningless for the
        start_time clock and must not be sent alongside a start_time filter: the two
        are AND-combined, which would re-introduce the very exclusion we avoid.
        """
        if self.time_field != "ingestion":
            return {}
        kwargs: dict = {}
        if self.before is not None:
            kwargs["to_time"] = self.before
        if self.after is not None:
            kwargs["from_time"] = self.after
        return kwargs

    def to_sdk_filters(self) -> list[TraceFilterPublic]:
        """Tag predicates, plus date bounds when on the start_time clock. AND-combined."""
        filters = [
            TraceFilterPublic(field="tags", operator="contains", value=tag) for tag in self.tags
        ]
        filters += [
            TraceFilterPublic(field="tags", operator="not_contains", value=tag)
            for tag in self.exclude_tags
        ]
        if self.time_field == "start_time":
            if self.before is not None:
                filters.append(
                    TraceFilterPublic(
                        field="start_time", operator="<", value=_fmt_dt(self.before)
                    )
                )
            if self.after is not None:
                filters.append(
                    TraceFilterPublic(field="start_time", operator=">", value=_fmt_dt(self.after))
                )
        return filters

    def sorting(self, direction: str) -> str:
        """Sort spec on whichever field the date bounds use, for the preview probes."""
        field = "start_time" if self.time_field == "start_time" else "id"
        return json.dumps([{"field": field, "direction": direction}])

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
        if (self.before or self.after) and self.time_field != DEFAULT_TIME_FIELD:
            parts.append(f"on {self.time_field} time")
        return " | ".join(parts) if parts else "(no filters)"

    @classmethod
    def from_config_filters(cls, f: dict) -> "TraceFilter":
        before = None
        if f.get("older_than_days"):
            before = datetime.now(tz=UTC) - timedelta(days=f["older_than_days"])
        elif f.get("before"):
            before = _parse_date(f["before"])
        after = _parse_date(f["after"]) if f.get("after") else None
        return cls(
            before=before,
            after=after,
            tags=list(f.get("tags") or []),
            exclude_tags=list(f.get("exclude_tags") or []),
            time_field=f.get("time_field", DEFAULT_TIME_FIELD),
        )

    def merge_from_args(self, args: argparse.Namespace) -> "TraceFilter":
        """Return a new filter with CLI args applied on top (CLI wins)."""
        result = dataclasses.replace(self)
        if getattr(args, "before", None):
            result.before = _parse_date(args.before)
        elif getattr(args, "older_than_days", None) is not None:
            result.before = datetime.now(tz=UTC) - timedelta(days=args.older_than_days)
        if getattr(args, "after", None):
            result.after = _parse_date(args.after)
        if getattr(args, "tag", None):
            result.tags = list(args.tag)
        if getattr(args, "exclude_tag", None):
            result.exclude_tags = list(args.exclude_tag)
        if getattr(args, "time_field", None):
            result.time_field = args.time_field
        return result

    def is_empty(self) -> bool:
        return self.before is None and self.after is None and not self.tags and not self.exclude_tags


def expand_ttl_rules(rules: list[dict]) -> list[tuple["TraceFilter", str]]:
    """
    Expand a ttl_rules list into (TraceFilter, label) pairs.

    Rules are sorted shortest-retention-first (most aggressive first). A rule
    listing several tags becomes one pass per tag, so its tags are matched as OR
    — unlike the `--tag` flag, which ANDs them. The catch-all rule (empty tags)
    excludes every tag named by an earlier rule so nothing is visited twice.
    """
    sorted_rules = sorted(rules, key=lambda r: r["older_than_days"])
    configured_tags: list[str] = []
    result: list[tuple[TraceFilter, str]] = []

    for rule in sorted_rules:
        days = rule["older_than_days"]
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        rule_tags: list[str] = rule.get("tags", [])
        rule_exclude: list[str] = rule.get("exclude_tags", [])

        if rule_tags:
            for tag in rule_tags:
                tf = TraceFilter(before=cutoff, tags=[tag], exclude_tags=list(rule_exclude))
                result.append((tf, f"tag={tag!r}, >{days}d old"))
            configured_tags.extend(rule_tags)
        else:
            tf = TraceFilter(before=cutoff, exclude_tags=configured_tags + rule_exclude)
            desc = rule.get("description", f"no configured tags, >{days}d old")
            result.append((tf, desc))

    return result


# ---------------------------------------------------------------------------
# 4. Project API
# ---------------------------------------------------------------------------


def get_all_projects(client: opik.Opik) -> list[dict]:
    """Return all projects in the workspace as list of {id, name} dicts."""
    projects: list[dict] = []
    page = 1
    while True:
        resp = _rl(
            lambda page=page: client.rest_client.projects.find_projects(page=page, size=100),
            "find_projects",
        )
        content = resp.content or []
        if not content:
            break
        projects.extend({"id": str(p.id), "name": p.name} for p in content)
        if len(projects) >= (resp.total or 0):
            break
        page += 1
    return projects


def resolve_projects(client: opik.Opik, names: list[str]) -> list[dict]:
    """
    Validate and resolve project names to {id, name} dicts.
    If names is empty, returns all projects in the workspace.
    Exits with an error if any named project is not found.
    """
    all_projects = get_all_projects(client)
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


def fetch_trace_count(client: opik.Opik, project_name: str, tf: TraceFilter) -> int:
    """Fast count-only query. Reads the 'total' field off a size=1 page."""
    # NOTE: no `exclude` here. The paginated endpoint rejects the field names the
    # streaming one accepts ("Invalid query param exclude 'input'"), and these calls
    # ask for a single row, so pruning fields would save nothing anyway.
    resp = _rl(
        lambda: client.rest_client.traces.get_traces_by_project(
            project_name=project_name,
            page=1,
            size=1,
            filters=tf.to_sdk_filters() or None,
            truncate=True,
            strip_attachments=True,
            **tf.to_api_kwargs(),
        ),
        "get_traces_by_project",
    )
    return resp.total or 0


def fetch_match_window(
    client: opik.Opik, project_name: str, tf: TraceFilter
) -> tuple[datetime | None, datetime | None]:
    """(oldest, newest) start_time among matching traces, sorted on the active clock.

    This is the operator's sanity check on the cutoff: if the newest trace about to
    be deleted is from yesterday, the filter is wrong. Shown for real before any
    deletion, so a mistaken cutoff is visible rather than inferred.
    """
    # NOTE: no `exclude` on these calls. The paginated endpoint rejects the field
    # names the streaming one accepts ("Invalid query param exclude 'input'"), and
    # each asks for a single row, so pruning fields would save nothing anyway.
    ends: list[datetime | None] = []
    for direction in ("ASC", "DESC"):
        resp = _rl(
            lambda d=direction: client.rest_client.traces.get_traces_by_project(
                project_name=project_name,
                page=1,
                size=1,
                filters=tf.to_sdk_filters() or None,
                truncate=True,
                strip_attachments=True,
                sorting=tf.sorting(d),
                **tf.to_api_kwargs(),
            ),
            "get_traces_by_project",
        )
        content = resp.content or []
        ends.append(content[0].start_time if content else None)
    return ends[0], ends[1]


def _search_page(
    client: opik.Opik,
    project_name: str,
    tf: TraceFilter,
    limit: int,
    cursor: str | None = None,
) -> list:
    """One page of matching traces, carrying only id + start_time.

    Pagination is by `last_retrieved_id` (a keyset cursor), never by page number.
    An offset cannot be used safely here: the delete loop mutates the result set
    as it goes, so any offset computed against the pre-delete set is stale.
    """
    def read() -> list:
        stream = client.rest_client.traces.search_traces(
            project_name=project_name,
            filters=tf.to_sdk_filters() or None,
            limit=limit,
            truncate=True,
            strip_attachments=True,
            exclude=EXCLUDE_FIELDS,
            last_retrieved_id=cursor,
            **tf.to_api_kwargs(),
        )
        return rest_stream_parser.read_and_parse_stream(
            stream=stream, item_class=trace_public.TracePublic
        )

    return _rl(read, "search_traces")


def delete_matching(
    client: opik.Opik,
    project_name: str,
    project_id: str | None,
    tf: TraceFilter,
    label: str = "",
) -> int:
    """Read a page, delete it, repeat until nothing matches.

    Deleting what we just read is what makes this terminate: the result set
    genuinely shrinks, so the next read returns the next traces rather than the
    same ones. Nothing is held in memory beyond the current page.
    """
    desc = f" ({label})" if label else ""
    print(f"  Deleting{desc} ...", flush=True)

    total_deleted = 0
    round_num = 0
    prev_first_id: str | None = None

    while True:
        page = _search_page(client, project_name, tf, SEARCH_PAGE_SIZE)
        if not page:
            break

        ids = [str(t.id) for t in page]

        # Progress guard: if a round returns the same head as the last one, the
        # previous deletes did not take effect and looping would spin forever.
        if prev_first_id is not None and ids[0] == prev_first_id:
            _fail(
                f"no progress deleting from {project_name!r} — "
                f"{len(ids)} traces still returned after a delete. Aborting this filter."
            )
            break
        prev_first_id = ids[0]

        round_num += 1
        for i in range(0, len(ids), DELETE_BATCH_SIZE):
            batch = ids[i : i + DELETE_BATCH_SIZE]
            _rl(
                lambda batch=batch: client.rest_client.traces.delete_traces(
                    ids=batch, project_id=project_id
                ),
                "delete_traces",
            )
            total_deleted += len(batch)

        print(f"    Round {round_num}: deleted {len(ids)} (running total: {total_deleted:,})")

    return total_deleted


# ---------------------------------------------------------------------------
# 6. Command Handlers
# ---------------------------------------------------------------------------


def cmd_list(client: opik.Opik, projects: list[dict], filters: list[tuple[TraceFilter, str]]) -> None:
    """Count-only inspection. No deletions."""
    print()
    grand_total = 0
    multi = len(filters) > 1

    errored = False
    for project in projects:
        name = project["name"]
        project_total = 0
        project_failed = False

        for tf, _label in filters:
            try:
                project_total += fetch_trace_count(client, name, tf)
            except ApiError as e:
                _fail(f"listing traces for {name!r}: {_api_msg(e)}")
                project_failed = True
                continue

        # A count we could not obtain is not a count of zero — say so, and keep it
        # out of the total rather than silently understating it.
        if project_failed:
            errored = True
            print(f"  {name:<40}  {'ERROR':>8}")
            continue

        print(f"  {name:<40}  {project_total:>8,} traces match")
        grand_total += project_total

    print()
    print("  " + "─" * 55)
    print(f"  Total: {grand_total:,} traces across {len(projects)} project(s)")
    if errored:
        print("  Some projects could not be counted (marked ERROR) and are excluded above.")
    if multi:
        print("  Note: TTL rules are counted per pass, so a trace carrying two")
        print("        listed tags is counted once per pass — treat as an upper bound.")
    print()


def _preview(
    client: opik.Opik, projects: list[dict], filters: list[tuple[TraceFilter, str]]
) -> int:
    """Count what would be deleted, and show the newest match per project."""
    grand = 0
    for project in projects:
        name = project["name"]
        for tf, label in filters:
            try:
                count = fetch_trace_count(client, name, tf)
            except ApiError as e:
                _fail(f"counting traces for {name!r}: {_api_msg(e)}")
                continue
            if not count:
                continue
            grand += count
            batches = (count + DELETE_BATCH_SIZE - 1) // DELETE_BATCH_SIZE
            print(f"  {name} — {count:,} traces ({label})")
            try:
                oldest, newest = fetch_match_window(client, name, tf)
                if oldest and newest:
                    clock = "start_time" if tf.time_field == "start_time" else "ingestion"
                    print(
                        f"      window       : {oldest:%Y-%m-%d %H:%M} → "
                        f"{newest:%Y-%m-%d %H:%M} UTC (by {clock})"
                    )
            except ApiError:
                pass  # Sanity line only — never fail a preview over it.
            print(f"      plan         : {batches} delete batch(es) of {DELETE_BATCH_SIZE}")
    return grand


def cmd_delete(
    client: opik.Opik,
    projects: list[dict],
    filters: list[tuple[TraceFilter, str]],
    dry_run: bool,
    yes: bool,
) -> None:
    """Delete (or preview) traces matching the filters across all projects."""
    print()

    if dry_run:
        total = _preview(client, projects, filters)
        print()
        print("  " + "=" * 58)
        print(f"  Grand total: {total:,} traces would be deleted across {len(projects)} project(s).")
        print("  No changes were made.")
        return

    if not yes:
        print("  Calculating scope...")
        total = _preview(client, projects, filters)
        print()
        print(f"  {total:,} traces would be deleted across {len(projects)} project(s).")
        if not total:
            print("  Nothing to do.")
            return
        print()
        if input("  Delete? [y/N] ").strip().lower() != "y":
            print("  Aborted.")
            return
        print()

    grand_total = 0
    for project in projects:
        name = project["name"]
        print(f"  {'=' * 58}")
        print(f"  Project: {name}")
        print(f"  {'=' * 58}")
        project_total = 0

        for tf, label in filters:
            try:
                project_total += delete_matching(client, name, project.get("id"), tf, label=label)
            except ApiError as e:
                _fail(f"deleting traces in {name!r}: {_api_msg(e)}")

        print(f"  Project subtotal: {project_total:,} traces")
        print()
        grand_total += project_total

    print(f"  {'=' * 58}")
    print(f"  Grand total: {grand_total:,} traces deleted across {len(projects)} project(s).")


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
    g.add_argument("--time-field", choices=["start_time", "ingestion"], metavar="FIELD",
                   help="Which clock the date bounds use. 'ingestion' (default) is when the "
                        "backend received the trace — server-assigned, so it answers 'how long "
                        "have we held this'. 'start_time' is the trace's own timestamp as shown "
                        "in the Opik UI, but is supplied by whatever wrote the trace; prefer it "
                        "only when the policy is about the age of the activity, not custody.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage_traces.py",
        description="Inspect and delete Opik traces by date range, tags, or TTL policies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Workflow:\n"
            "  1. python manage_traces.py list  [filter flags]             # inspect counts\n"
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

    project_names: list[str] = list(getattr(args, "projects", None) or cfg.get("projects") or [])

    # A top-level time_field applies to every pass; CLI --time-field still wins.
    cfg_time_field = cfg.get("time_field")

    if cfg.get("ttl_rules"):
        ttl_filters = expand_ttl_rules(cfg["ttl_rules"])
        out = []
        for tf, label in ttl_filters:
            if cfg_time_field:
                tf = dataclasses.replace(tf, time_field=cfg_time_field)
            out.append((tf.merge_from_args(args), label))
        return project_names, out

    base_tf = TraceFilter()
    if cfg.get("filters"):
        base_tf = TraceFilter.from_config_filters(cfg["filters"])
    if cfg_time_field and not (cfg.get("filters") or {}).get("time_field"):
        base_tf = dataclasses.replace(base_tf, time_field=cfg_time_field)

    final_tf = base_tf.merge_from_args(args)

    if final_tf.is_empty():
        _die(
            "No filter criteria specified.\n"
            "Use --older-than-days, --before, --after, --tag, --exclude-tag, or a --config file."
        )

    return project_names, [(final_tf, final_tf.describe())]


def _print_header(
    env: dict,
    cmd: str,
    projects: list[dict],
    filters: list[tuple[TraceFilter, str]],
    dry_run: bool = False,
) -> None:
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
        for _tf, label in filters:
            print(f"              {label}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate config before touching the network or requiring env vars
    project_names, filters = _resolve_filters(args)

    client, env = get_client()

    print("Resolving projects...", flush=True)
    try:
        projects = resolve_projects(client, project_names)
    except ApiError as e:
        _die(f"Cannot list projects in workspace {env['workspace']!r}: {_api_msg(e)}")

    _print_header(env, args.cmd, projects, filters, dry_run=getattr(args, "dry_run", False))

    if args.cmd == "list":
        cmd_list(client, projects, filters)
    elif args.cmd == "delete":
        cmd_delete(client, projects, filters, dry_run=args.dry_run, yes=args.yes)

    if _FAILED:
        print("\nCompleted with errors — see messages above.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _rl(call, operation_name: str):
    """Run an API call, waiting out HTTP 429s per the server's Retry-After.

    Every call goes through here. A retention sweep over a large workspace will be
    rate limited eventually, and unattended runs should pace themselves rather than
    fail — the operator is expected to bound total runtime with `timeout` (see README).
    """
    return rest_helpers.ensure_rest_api_call_respecting_rate_limit(
        rest_callable=call, operation_name=operation_name
    )


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _fail(msg: str) -> None:
    """Report a recoverable error and mark the run as failed."""
    global _FAILED
    _FAILED = True
    print(f"  ERROR {msg}", file=sys.stderr)


def _api_msg(exc: ApiError) -> str:
    return f"HTTP {exc.status_code}: {exc.body}"


if __name__ == "__main__":
    main()
