#!/usr/bin/env python3
"""Create and manage Opik online evaluation rules via the SDK and REST API, side by side.

Workflow:
  1. Dry-run   →  uv run create-online-eval-rules create-llm-judge --dry-run   (prints SDK + curl)
  2. Execute   →  set OPIK_API_KEY + OPIK_WORKSPACE, then  uv run create-online-eval-rules create-llm-judge
"""

import argparse
import os
import sys

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_URL = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api").rstrip("/")
DEFAULT_PROJECT = os.environ.get("OPIK_PROJECT_NAME", "online-eval-rules-example")

EVALUATORS_PATH = "/v1/private/automations/evaluators"
PLACEHOLDER_PROJECT_ID = "00000000-0000-0000-0000-000000000000"

RULE_LLM_JUDGE = "llm_as_judge"
RULE_PY = "user_defined_metric_python"
RULE_THREAD_JUDGE = "trace_thread_llm_as_judge"
RULE_SPAN_JUDGE = "span_llm_as_judge"
RULE_SPAN_PY = "span_user_defined_metric_python"

DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--surface", choices=["sdk", "rest"], default="sdk",
                       help="Which surface runs on a live call (default: sdk). DRY_RUN always prints both.")
        p.add_argument("--project", default=DEFAULT_PROJECT, help="Project name (created if absent).")
        p.add_argument("--dry-run", action="store_true", help="Print SDK + curl; touch nothing.")

    def add_create(p: argparse.ArgumentParser) -> None:
        add_common(p)
        p.add_argument("--name", required=True, help="Rule name.")
        p.add_argument("--model", default="gpt-4o", help="Judge model (LLM-as-judge rules).")
        p.add_argument("--sampling-rate", type=float, default=1.0, help="Fraction of items scored (0.0-1.0).")

    add_create(sub.add_parser("create-llm-judge", help="Trace-level LLM-as-judge rule."))
    add_create(sub.add_parser("create-python", help="Trace-level user-defined Python metric rule."))
    add_create(sub.add_parser("create-thread", help="Thread-level LLM-as-judge rule."))
    span = sub.add_parser("create-span", help="Span-level rule (LLM-judge, or --python for a metric).")
    add_create(span)
    span.add_argument("--python", action="store_true", help="Span-level Python metric instead of LLM-judge.")

    p_list = sub.add_parser("list", help="List rules in the project.")
    add_common(p_list)

    p_get = sub.add_parser("get", help="Get one rule by id.")
    add_common(p_get)
    p_get.add_argument("--id", required=True, help="Rule id (UUID).")

    p_upd = sub.add_parser("update", help="Update a rule's sampling rate and/or enabled flag.")
    add_common(p_upd)
    p_upd.add_argument("--id", required=True, help="Rule id (UUID).")
    p_upd.add_argument("--sampling-rate", type=float, default=None, help="New sampling rate.")
    enabled = p_upd.add_mutually_exclusive_group()
    enabled.add_argument("--enabled", dest="enabled", action="store_true", default=None)
    enabled.add_argument("--disabled", dest="enabled", action="store_false", default=None)

    p_del = sub.add_parser("delete", help="Delete a rule by id.")
    add_common(p_del)
    p_del.add_argument("--id", required=True, help="Rule id (UUID).")
    p_del.add_argument("--yes", action="store_true", help="Confirm deletion on a live run.")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    dry_run = DRY_RUN or getattr(args, "dry_run", False)
    if dry_run and not getattr(args, "dry_run", False):
        print("OPIK_API_KEY / OPIK_WORKSPACE not set — running in DRY_RUN.", file=sys.stderr)
    print(f"[stub] command={args.command} dry_run={dry_run}")  # replaced in Task 8
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
