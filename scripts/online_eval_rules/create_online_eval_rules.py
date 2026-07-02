#!/usr/bin/env python3
"""Create and manage Opik online evaluation rules via the SDK and REST API, side by side.

Workflow:
  1. Dry-run   →  uv run create-online-eval-rules create-llm-judge --dry-run   (prints SDK + curl)
  2. Execute   →  set OPIK_API_KEY + OPIK_WORKSPACE, then  uv run create-online-eval-rules create-llm-judge
"""

import argparse
import json
import os
import pathlib
import pprint
import sys

import requests

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

    def add_common(p: argparse.ArgumentParser, *, surface: bool = True) -> None:
        if surface:
            p.add_argument("--surface", choices=["sdk", "rest"], default="sdk",
                           help="Surface for a live call (default: sdk). DRY_RUN always prints both.")
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

    p_upd = sub.add_parser("update",
                           help="Update a rule's sampling rate and/or enabled flag (always uses REST).")
    add_common(p_upd, surface=False)  # update has no SDK path; don't offer a --surface no-op
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


_CREATE_COMMANDS = {
    "create-llm-judge": RULE_LLM_JUDGE,
    "create-python": RULE_PY,
    "create-thread": RULE_THREAD_JUDGE,
    "create-span": RULE_SPAN_JUDGE,  # overridden to RULE_SPAN_PY when --python is set
}


def _rule_type_for_args(args) -> str:
    rule_type = _CREATE_COMMANDS[args.command]
    if args.command == "create-span" and getattr(args, "python", False):
        return RULE_SPAN_PY
    return rule_type


def _print_both_surfaces(payload: dict) -> None:
    print("── Python SDK ──")
    print(render_sdk_snippet(payload))
    print("\n── REST (curl) ──")
    print(render_curl(payload))


def _dispatch_create(args, dry_run: bool) -> int:
    rule_type = _rule_type_for_args(args)
    if dry_run:
        payload = build_payload(rule_type, name=args.name, project_id=PLACEHOLDER_PROJECT_ID,
                                sampling_rate=args.sampling_rate, model=args.model)
        _print_both_surfaces(payload)
        return 0

    import opik
    client = opik.Opik()
    project_id = resolve_project_id(client, args.project)
    payload = build_payload(rule_type, name=args.name, project_id=project_id,
                            sampling_rate=args.sampling_rate, model=args.model)
    try:
        if args.surface == "sdk":
            via_sdk(client, "create", payload=payload)
        else:
            via_rest("create", payload=payload)
    except Exception as exc:  # noqa: BLE001 — surface an actionable message to the client
        msg = str(exc)
        if "llm_as_judge" in rule_type and ("provider" in msg.lower() or "api key" in msg.lower()):
            print("Create failed: this workspace has no LLM provider key configured. "
                  "Add one in Opik → Configuration → AI providers, then retry.", file=sys.stderr)
        raise
    try:
        created = via_rest("list", project_id=project_id)
        print(f"Created rule '{args.name}' in project '{args.project}'. Current rules:")
        print(json.dumps(created, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        print(f"Rule created; could not list rules: {exc}", file=sys.stderr)
    return 0


def _dump(result) -> str:
    """JSON-print a result from either surface. REST returns a dict; the SDK returns a
    pydantic model, which json.dumps can't serialise (default=str would collapse it to a
    single repr string), so unwrap it with model_dump first."""
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    return json.dumps(result, indent=2, default=str)


def _dispatch_manage(args, dry_run: bool) -> int:
    if dry_run:
        # update has no --surface (always REST); other manage commands default to sdk.
        surface = getattr(args, "surface", None) or "rest"
        print(f"[DRY RUN] would '{args.command}' via {surface} at {OPIK_URL}{EVALUATORS_PATH}")
        if args.command == "delete":
            print("[DRY RUN] delete requires --yes on a live run.")
        return 0

    import opik
    client = opik.Opik()
    project_id = resolve_project_id(client, args.project)

    if args.command == "list":
        result = (via_sdk(client, "list", project_id=project_id) if args.surface == "sdk"
                  else via_rest("list", project_id=project_id))
        print(_dump(result))
        return 0
    if args.command == "get":
        result = (via_sdk(client, "get", rule_id=args.id, project_id=project_id) if args.surface == "sdk"
                  else via_rest("get", rule_id=args.id, project_id=project_id))
        print(_dump(result))
        return 0
    if args.command == "update":
        current = via_rest("get", rule_id=args.id, project_id=project_id)
        # The evaluators PATCH endpoint requires at least one project on every update
        # (400 "At least one project must be specified" otherwise), so carry it forward.
        patch = {"name": current["name"], "type": current["type"], "action": "evaluator",
                 "project_ids": [current.get("project_id") or project_id]}
        if current.get("code") is not None:
            patch["code"] = current["code"]
        if args.sampling_rate is not None:
            patch["sampling_rate"] = args.sampling_rate
        if args.enabled is not None:
            patch["enabled"] = args.enabled
        via_rest("update", rule_id=args.id, payload=patch)
        carried = ("name", "type", "action", "project_ids", "code")
        changed = {k: v for k, v in patch.items() if k not in carried}
        print(f"Updated rule {args.id}: {json.dumps(changed)}")
        return 0
    if args.command == "delete":
        if not args.yes:
            print("Refusing to delete without --yes.", file=sys.stderr)
            return 1
        if args.surface == "sdk":
            via_sdk(client, "delete", rule_id=args.id, project_id=project_id)
        else:
            via_rest("delete", rule_id=args.id, project_id=project_id)
        print(f"Deleted rule {args.id}.")
        return 0
    raise ValueError(f"unknown command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    dry_run = DRY_RUN or getattr(args, "dry_run", False)
    if dry_run and not getattr(args, "dry_run", False):
        print("OPIK_API_KEY / OPIK_WORKSPACE not set — running in DRY_RUN.", file=sys.stderr)

    if args.command in _CREATE_COMMANDS:
        return _dispatch_create(args, dry_run)
    return _dispatch_manage(args, dry_run)


_JUDGE_SYSTEM = (
    "You are a strict evaluation judge. Assess the ANSWER against the QUESTION. "
    "Return only the fields defined by the output schema."
)
_JUDGE_USER = (
    "QUESTION:\n{{input}}\n\nANSWER:\n{{output}}\n\n"
    "Score relevance from 1 (irrelevant) to 5 (fully relevant), and whether the answer is "
    "grounded in the question."
)
_JUDGE_SCHEMA = [
    {"name": "relevance_score", "type": "INTEGER", "description": "Relevance, 1 (low) to 5 (high)."},
    {"name": "is_grounded", "type": "BOOLEAN", "description": "True if the answer is grounded in the input."},
]
_METRIC_SOURCE_PATH = pathlib.Path(__file__).resolve().parent / "metric_example.py"


def _judge_code(model: str, *, with_variables: bool) -> dict:
    code: dict = {
        "model": {"name": model, "temperature": 0.0},
        "messages": [
            {"role": "SYSTEM", "content": _JUDGE_SYSTEM},
            {"role": "USER", "content": _JUDGE_USER},
        ],
        "schema": [dict(field) for field in _JUDGE_SCHEMA],
    }
    if with_variables:
        code["variables"] = {"input": "input.question", "output": "output.output"}
    return code


def _python_code() -> dict:
    return {
        "metric": _METRIC_SOURCE_PATH.read_text(encoding="utf-8"),
        "arguments": {"output": "output.output", "reference": "input.expected"},
    }


def build_payload(rule_type: str, *, name: str, project_id: str,
                  sampling_rate: float, model: str) -> dict:
    payload: dict = {
        "name": name,
        "project_ids": [project_id],
        "sampling_rate": sampling_rate,
        "enabled": True,
        "action": "evaluator",
        "type": rule_type,
    }
    if rule_type == RULE_LLM_JUDGE:
        payload["code"] = _judge_code(model, with_variables=True)
    elif rule_type == RULE_SPAN_JUDGE:
        payload["code"] = _judge_code(model, with_variables=True)
    elif rule_type == RULE_THREAD_JUDGE:
        payload["code"] = _judge_code(model, with_variables=False)
    elif rule_type in (RULE_PY, RULE_SPAN_PY):
        payload["code"] = _python_code()
    else:
        raise ValueError(f"unknown rule_type: {rule_type}")
    return payload


_SDK_VARIANT_NAME = {
    RULE_LLM_JUDGE: "AutomationRuleEvaluatorWrite_LlmAsJudge",
    RULE_PY: "AutomationRuleEvaluatorWrite_UserDefinedMetricPython",
    RULE_THREAD_JUDGE: "AutomationRuleEvaluatorWrite_TraceThreadLlmAsJudge",
    RULE_SPAN_JUDGE: "AutomationRuleEvaluatorWrite_SpanLlmAsJudge",
    RULE_SPAN_PY: "AutomationRuleEvaluatorWrite_SpanUserDefinedMetricPython",
}


def render_curl(payload: dict) -> str:
    body = json.dumps(payload, indent=2)
    safe = body.replace("'", "'\\''")
    return (
        f'curl -X POST "{OPIK_URL}{EVALUATORS_PATH}/" \\\n'
        f'  -H "Authorization: Bearer $OPIK_API_KEY" \\\n'
        f'  -H "Comet-Workspace: $OPIK_WORKSPACE" \\\n'
        f'  -H "Content-Type: application/json" \\\n'
        f"  -d '{safe}'"
    )


def render_sdk_snippet(payload: dict) -> str:
    variant = _SDK_VARIANT_NAME[payload["type"]]
    body = pprint.pformat(_coerce_payload_for_sdk(payload), sort_dicts=False, width=100)
    return (
        "import opik\n"
        f"from opik.rest_api.types import {variant}\n\n"
        "client = opik.Opik()\n"
        f"request = {variant}.model_validate({body})\n"
        "client.rest_client.automation_rule_evaluators.create_automation_rule_evaluator(request=request)"
    )


def _rest_headers() -> dict:
    return {
        "Authorization": f"Bearer {OPIK_API_KEY}",
        "Comet-Workspace": OPIK_WORKSPACE or "",
        "Content-Type": "application/json",
    }


def _check(resp) -> None:
    if resp.status_code >= 300:
        raise RuntimeError(f"Opik REST error {resp.status_code}: {resp.text}")


def via_rest(op: str, *, payload=None, rule_id=None, project_id=None, session=None):
    http = session or requests
    base = f"{OPIK_URL}{EVALUATORS_PATH}"
    headers = _rest_headers()

    if op == "create":
        resp = http.post(f"{base}/", headers=headers, json=payload)
        _check(resp)
        return resp
    if op == "list":
        resp = http.get(f"{base}/", headers=headers, params={"project_id": project_id})
        _check(resp)
        return resp.json()
    if op == "get":
        resp = http.get(f"{base}/{rule_id}", headers=headers, params={"project_id": project_id})
        _check(resp)
        return resp.json()
    if op == "update":
        resp = http.patch(f"{base}/{rule_id}", headers=headers, json=payload)
        _check(resp)
        return resp
    if op == "delete":
        # Pass project_id to match the SDK's delete_automation_rule_evaluator_batch, which scopes
        # the batch delete by project; requests drops params whose value is None.
        resp = http.post(f"{base}/delete", headers=headers, json={"ids": [rule_id]},
                         params={"project_id": project_id})
        _check(resp)
        return resp
    raise ValueError(f"unknown op: {op}")


def _sdk_variant_classes() -> dict:
    from opik.rest_api.types import (
        AutomationRuleEvaluatorWrite_LlmAsJudge,
        AutomationRuleEvaluatorWrite_SpanLlmAsJudge,
        AutomationRuleEvaluatorWrite_SpanUserDefinedMetricPython,
        AutomationRuleEvaluatorWrite_TraceThreadLlmAsJudge,
        AutomationRuleEvaluatorWrite_UserDefinedMetricPython,
    )
    return {
        RULE_LLM_JUDGE: AutomationRuleEvaluatorWrite_LlmAsJudge,
        RULE_PY: AutomationRuleEvaluatorWrite_UserDefinedMetricPython,
        RULE_THREAD_JUDGE: AutomationRuleEvaluatorWrite_TraceThreadLlmAsJudge,
        RULE_SPAN_JUDGE: AutomationRuleEvaluatorWrite_SpanLlmAsJudge,
        RULE_SPAN_PY: AutomationRuleEvaluatorWrite_SpanUserDefinedMetricPython,
    }


def _coerce_payload_for_sdk(payload: dict) -> dict:
    """Rename the ``schema`` key in the ``code`` sub-dict to ``schema_``.

    The Opik SDK's LLM-judge code types store the output schema in a field
    named ``schema_`` (Python reserves ``schema`` as a Pydantic class method).
    The ``FieldMetadata(alias="schema")`` annotation only controls *serialisation*
    (JSON output), not *deserialisation* — pydantic's ``model_validate`` looks up
    fields by their Python name, so the ``schema`` key from ``build_payload`` must
    be renamed to ``schema_`` before the SDK class can be instantiated.
    """
    if "code" not in payload or not isinstance(payload["code"], dict):
        return payload
    code = payload["code"]
    if "schema" not in code:
        return payload
    fixed_code = dict(code)
    fixed_code["schema_"] = fixed_code.pop("schema")
    return {**payload, "code": fixed_code}


def build_sdk_request(payload: dict):
    cls = _sdk_variant_classes()[payload["type"]]
    return cls.model_validate(_coerce_payload_for_sdk(payload))


def via_sdk(client, op: str, *, payload=None, rule_id=None, project_id=None, session=None):
    api = client.rest_client.automation_rule_evaluators
    if op == "create":
        return api.create_automation_rule_evaluator(request=build_sdk_request(payload))
    if op == "list":
        return api.find_evaluators(project_id=project_id)
    if op == "get":
        return api.get_evaluator_by_id(rule_id, project_id=project_id)
    if op == "delete":
        return api.delete_automation_rule_evaluator_batch(ids=[rule_id], project_id=project_id)
    raise ValueError(f"unsupported sdk op: {op}")


def resolve_project_id(client, name: str) -> str:
    projects = client.rest_client.projects
    page = projects.find_projects(name=name)
    if not page.content:
        projects.create_project(name=name)
        page = projects.find_projects(name=name)
    for project in page.content:
        if project.name == name:
            return project.id
    if page.content:
        return page.content[0].id
    raise RuntimeError(f"Could not resolve or create project '{name}'.")


if __name__ == "__main__":
    raise SystemExit(main())
