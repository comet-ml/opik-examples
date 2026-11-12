"""Tests for the idempotent Opik setup, using stub clients (no network)."""

from types import SimpleNamespace
from typing import Any

import pytest
from opik.rest_api.core.api_error import ApiError
from opik.rest_api.types import AutomationRuleEvaluatorWrite_LlmAsJudge

import setup_opik
from config import ONLINE_RULE_NAME, TEST_SUITE_NAME, TRAFFIC_TAG
from scenarios import SCENARIOS


def _rules_client(existing: list[str], created: list[Any]) -> SimpleNamespace:
    def find_evaluators(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(content=[SimpleNamespace(name=n) for n in existing])

    api = SimpleNamespace(
        find_evaluators=find_evaluators,
        create_automation_rule_evaluator=lambda *, request: created.append(request),
    )
    return SimpleNamespace(rest_client=SimpleNamespace(automation_rule_evaluators=api))


def test_ensure_environments_creates_only_missing() -> None:
    created: list[str] = []
    client = SimpleNamespace(
        get_environments=lambda: [SimpleNamespace(name="staging")],
        create_environment=lambda name, **_k: created.append(name),
    )
    assert setup_opik.ensure_environments(client, ["staging", "production"]) == ["production"]
    assert created == ["production"]


def test_ensure_online_rule_skips_existing_by_exact_name() -> None:
    created: list[Any] = []
    assert setup_opik.ensure_online_rule(_rules_client([ONLINE_RULE_NAME], created), "pid", "m") is False
    assert created == []


def test_ensure_online_rule_ignores_near_name() -> None:
    created: list[Any] = []
    client = _rules_client([f"{ONLINE_RULE_NAME}-old"], created)
    assert setup_opik.ensure_online_rule(client, "pid", "gpt-4o-mini") is True
    assert isinstance(created[0], AutomationRuleEvaluatorWrite_LlmAsJudge)
    assert created[0].name == ONLINE_RULE_NAME


def test_rule_payload_scopes_to_traffic_and_maps_variables() -> None:
    p = setup_opik.build_rule_payload("pid", "gpt-4o-mini")
    assert p["name"] == ONLINE_RULE_NAME
    assert p["project_ids"] == ["pid"]
    assert p["sampling_rate"] == 1.0
    assert p["trigger_scope"] == "production"
    assert p["filters"] == [{"field": "tags", "operator": "contains", "value": TRAFFIC_TAG}]
    assert p["code"]["variables"] == {"input": "input.scenario", "output": "output.plan"}
    assert p["code"]["model"]["name"] == "gpt-4o-mini"
    assert [s["name"] for s in p["code"]["schema"]] == ["plan_consistent"]
    assert p["code"]["schema"][0]["type"] == "BOOLEAN"


def test_rule_payload_builds_sdk_model() -> None:
    request = setup_opik.build_rule_request(setup_opik.build_rule_payload("pid", "gpt-4o-mini"))
    assert isinstance(request, AutomationRuleEvaluatorWrite_LlmAsJudge)
    assert request.code is not None and request.code.schema_[0].name == "plan_consistent"


def test_test_suite_uses_guardrails_and_policy() -> None:
    seen: dict[str, Any] = {}
    suite = SimpleNamespace(
        insert=lambda items, deduplication=True: seen.update(items=items, dedup=deduplication)
    )

    def get_or_create_test_suite(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return suite

    client = SimpleNamespace(get_or_create_test_suite=get_or_create_test_suite)
    assert setup_opik.ensure_test_suite(client) is suite
    assert seen["name"] == TEST_SUITE_NAME
    assert seen["global_assertions"] == list(setup_opik.GUARDRAIL_ASSERTIONS)
    assert seen["global_execution_policy"] == {"runs_per_item": 2, "pass_threshold": 1}
    assert seen["items"] == [{"data": {"input": s["input"]}} for s in SCENARIOS[:8]]
    assert seen["dedup"] is True


def test_resolve_project_id_creates_on_404() -> None:
    created: list[str] = []

    def retrieve_project(*, name: str) -> SimpleNamespace:
        if not created:
            raise ApiError(status_code=404, body="not found")
        return SimpleNamespace(id="p1", name=name)

    projects = SimpleNamespace(
        retrieve_project=retrieve_project, create_project=lambda *, name: created.append(name)
    )
    client = SimpleNamespace(rest_client=SimpleNamespace(projects=projects))
    assert setup_opik.resolve_project_id(client, "eval-in-ci-example") == "p1"
    assert created == ["eval-in-ci-example"]


def test_resolve_project_id_reraises_other_errors() -> None:
    def retrieve_project(*, name: str) -> SimpleNamespace:
        raise ApiError(status_code=401, body="unauthorized")

    projects = SimpleNamespace(retrieve_project=retrieve_project, create_project=lambda *, name: None)
    client = SimpleNamespace(rest_client=SimpleNamespace(projects=projects))
    with pytest.raises(ApiError):
        setup_opik.resolve_project_id(client, "eval-in-ci-example")
