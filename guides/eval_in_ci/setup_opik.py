"""Idempotent Opik setup: environments, dataset, test suite and the online evaluation rule."""

# WHY: the evaluate step runs this on every dispatch, so any run label works on a fresh workspace and
# a second run changes nothing.

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from opik.rest_api.core.api_error import ApiError
from opik.rest_api.types import AutomationRuleEvaluatorWrite_LlmAsJudge

from config import (
    DATASET_NAME,
    ENV_PRODUCTION,
    JUDGE_MODEL,
    ONLINE_RULE_NAME,
    PROJECT_NAME,
    TEST_SUITE_NAME,
    TRAFFIC_TAG,
)
from scenarios import SCENARIOS

GUARDRAIL_ASSERTIONS: tuple[str, ...] = (
    "The output is a single JSON object with exactly the keys actors, maneuver and parameters, "
    "and no other text.",
    "The actors list starts with ego.",
    "Every number in parameters appears in the input text.",
)
# WHY: the assertions are LLM-judged, so an item passes when either of two runs passes; one noisy
# judge call does not block a promotion.
SUITE_POLICY = {"runs_per_item": 2, "pass_threshold": 1}
SUITE_ITEMS = 8

_JUDGE_SYSTEM = (
    "You are a strict evaluation judge for a driving-scenario planner. "
    "Return only the fields defined by the output schema."
)
_JUDGE_USER = (
    "SCENARIO:\n{{input}}\n\nPLAN:\n{{output}}\n\n"
    "Is the plan consistent with the scenario: the right actors, a fitting maneuver, and the speed "
    "and gap stated in the scenario?"
)
_JUDGE_SCHEMA = [
    {"name": "plan_consistent", "type": "BOOLEAN", "description": "The plan matches the scenario text"},
]


@dataclass(frozen=True)
class SetupReport:
    dataset: Any
    project_id: str
    created: list[str]


def ensure_environments(client: Any, names: Sequence[str]) -> list[str]:
    """Register the environments that do not exist yet; return the ones created."""
    existing = {env.name for env in client.get_environments()}
    created = [name for name in names if name not in existing]
    for name in created:
        client.create_environment(name=name, description=f"{name} prompts for the eval-in-CI guide")
    return created


def ensure_dataset(client: Any) -> Any:
    """Get or create the dataset; insert() dedups by content, so re-runs add nothing."""
    dataset = client.get_or_create_dataset(
        name=DATASET_NAME, description="Driving scenarios for the eval-in-CI guide"
    )
    dataset.insert(SCENARIOS)
    return dataset


def ensure_test_suite(client: Any) -> Any:
    """Get or create the guardrail test suite and insert its items (deduplicated)."""
    suite = client.get_or_create_test_suite(
        name=TEST_SUITE_NAME,
        description="Format and grounding checks a prompt must pass before staging",
        global_assertions=list(GUARDRAIL_ASSERTIONS),
        global_execution_policy=SUITE_POLICY,
    )
    suite.insert([{"data": {"input": s["input"]}} for s in SCENARIOS[:SUITE_ITEMS]], deduplication=True)
    return suite


def resolve_project_id(client: Any, name: str) -> str:
    """Exact-name project lookup, creating the project when it is missing."""
    projects = client.rest_client.projects
    try:
        return projects.retrieve_project(name=name).id
    except ApiError as exc:
        if exc.status_code != 404:
            raise
    projects.create_project(name=name)
    return projects.retrieve_project(name=name).id


def build_rule_payload(project_id: str, model: str) -> dict[str, Any]:
    """LLM-as-judge rule that scores only the simulated production traffic."""
    return {
        "name": ONLINE_RULE_NAME,
        "project_ids": [project_id],
        "sampling_rate": 1.0,
        "enabled": True,
        "action": "evaluator",
        "type": "llm_as_judge",
        # WHY: production scope means SDK-logged traces; the tag filter skips the optimizer's own calls.
        "trigger_scope": "production",
        "filters": [{"field": "tags", "operator": "contains", "value": TRAFFIC_TAG}],
        "code": {
            "model": {"name": model, "temperature": 0.0},
            "messages": [
                {"role": "SYSTEM", "content": _JUDGE_SYSTEM},
                {"role": "USER", "content": _JUDGE_USER},
            ],
            "variables": {"input": "input.scenario", "output": "output.plan"},
            "schema": [dict(entry) for entry in _JUDGE_SCHEMA],
        },
    }


# WHY: the SDK type stores the output schema as `schema_`; the alias only applies when serialising.
def build_rule_request(payload: dict[str, Any]) -> AutomationRuleEvaluatorWrite_LlmAsJudge:
    code = dict(payload["code"])
    code["schema_"] = code.pop("schema")
    return AutomationRuleEvaluatorWrite_LlmAsJudge.model_validate({**payload, "code": code})


def ensure_online_rule(client: Any, project_id: str, model: str) -> bool:
    """Create the online rule unless one with the exact name exists; return True when created."""
    api = client.rest_client.automation_rule_evaluators
    page = api.find_evaluators(project_id=project_id, name=ONLINE_RULE_NAME)
    if any(rule.name == ONLINE_RULE_NAME for rule in page.content or []):
        return False
    api.create_automation_rule_evaluator(request=build_rule_request(build_rule_payload(project_id, model)))
    return True


def run_setup(client: Any) -> SetupReport:
    created = ensure_environments(client, [ENV_PRODUCTION])
    dataset = ensure_dataset(client)
    ensure_test_suite(client)
    project_id = resolve_project_id(client, PROJECT_NAME)
    if ensure_online_rule(client, project_id, JUDGE_MODEL):
        created.append(ONLINE_RULE_NAME)
    return SetupReport(dataset=dataset, project_id=project_id, created=created)
