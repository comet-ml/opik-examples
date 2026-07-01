import ast
import importlib
import json
import sys

import pytest

import create_online_eval_rules as cli


def test_parser_parses_create_llm_judge():
    args = cli.build_parser().parse_args(["create-llm-judge", "--name", "r1", "--dry-run"])
    assert args.command == "create-llm-judge"
    assert args.name == "r1"
    assert args.dry_run is True


def test_parser_defaults_surface_to_sdk():
    args = cli.build_parser().parse_args(["list"])
    assert args.surface == "sdk"


def test_build_payload_llm_judge_shape():
    p = cli.build_payload(cli.RULE_LLM_JUDGE, name="rel", project_id="pid",
                          sampling_rate=0.5, model="gpt-4o")
    assert p["type"] == "llm_as_judge"
    assert p["action"] == "evaluator"
    assert p["project_ids"] == ["pid"]
    assert p["sampling_rate"] == 0.5
    assert p["enabled"] is True
    assert p["code"]["model"]["name"] == "gpt-4o"
    assert p["code"]["variables"]  # trace judge maps variables
    types = {f["type"] for f in p["code"]["schema"]}
    assert types <= {"BOOLEAN", "INTEGER", "DOUBLE"}  # STRING is forbidden by the API
    assert {m["role"] for m in p["code"]["messages"]} <= {"SYSTEM", "USER", "AI",
                                                          "TOOL_EXECUTION_RESULT", "CUSTOM"}


def test_build_payload_thread_judge_omits_variables():
    p = cli.build_payload(cli.RULE_THREAD_JUDGE, name="t", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    assert p["type"] == "trace_thread_llm_as_judge"
    assert "variables" not in p["code"]


def test_build_payload_python_embeds_metric_source():
    p = cli.build_payload(cli.RULE_PY, name="eq", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    assert p["type"] == "user_defined_metric_python"
    assert "class" in p["code"]["metric"] and "BaseMetric" in p["code"]["metric"]
    assert set(p["code"]["arguments"]) == {"output", "reference"}


def test_build_payload_span_python_via_flag_type():
    p = cli.build_payload(cli.RULE_SPAN_PY, name="s", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    assert p["type"] == "span_user_defined_metric_python"
    assert "metric" in p["code"]


def test_build_payload_is_json_serializable():
    for rt in (cli.RULE_LLM_JUDGE, cli.RULE_PY, cli.RULE_THREAD_JUDGE,
               cli.RULE_SPAN_JUDGE, cli.RULE_SPAN_PY):
        json.dumps(cli.build_payload(rt, name="x", project_id="pid",
                                     sampling_rate=1.0, model="gpt-4o"))


def test_render_curl_has_path_headers_and_valid_json():
    p = cli.build_payload(cli.RULE_LLM_JUDGE, name="r", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    out = cli.render_curl(p)
    assert "/v1/private/automations/evaluators/" in out
    assert "Authorization: Bearer $OPIK_API_KEY" in out
    assert "Comet-Workspace: $OPIK_WORKSPACE" in out
    body = out.split("-d '", 1)[1].rsplit("'", 1)[0]
    assert json.loads(body)["type"] == "llm_as_judge"


def test_render_curl_apostrophe_in_name():
    p = cli.build_payload(cli.RULE_LLM_JUDGE, name="O'Brien", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    out = cli.render_curl(p)
    # The shell-safe escape sequence must appear
    assert "'\\''" in out
    # No bare unescaped apostrophe inside the JSON value (between -d ' and the closing ')
    # Extract the body between -d ' and last '
    body_part = out.split("-d '", 1)[1].rsplit("'", 1)[0]
    # Reconstruct: replacing the shell-escape back to get the actual JSON
    json_str = body_part.replace("'\\''", "'")
    data = json.loads(json_str)
    assert data["name"] == "O'Brien"


def test_render_sdk_snippet_names_variant():
    p = cli.build_payload(cli.RULE_SPAN_PY, name="r", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    out = cli.render_sdk_snippet(p)
    assert "AutomationRuleEvaluatorWrite_SpanUserDefinedMetricPython" in out
    assert "create_automation_rule_evaluator" in out


def test_render_sdk_snippet_payload_is_valid_python_and_validates():
    import pprint as _pprint

    from opik.rest_api import types as _t
    for rt in (cli.RULE_LLM_JUDGE, cli.RULE_PY, cli.RULE_THREAD_JUDGE, cli.RULE_SPAN_JUDGE, cli.RULE_SPAN_PY):
        p = cli.build_payload(rt, name="r", project_id="pid", sampling_rate=1.0, model="gpt-4o")
        coerced = cli._coerce_payload_for_sdk(p)
        assert ast.literal_eval(_pprint.pformat(coerced, sort_dicts=False)) == coerced  # no true/false/null
        variant = getattr(_t, cli._SDK_VARIANT_NAME[rt])
        assert variant.model_validate(coerced).name == "r"                               # schema_ present


class _FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.calls = []

    def _record(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return _FakeResp(200, {"content": [], "url": url})

    def post(self, url, **kw):
        return self._record("POST", url, **kw)

    def get(self, url, **kw):
        return self._record("GET", url, **kw)

    def patch(self, url, **kw):
        return self._record("PATCH", url, **kw)


def test_via_rest_create_posts_to_collection():
    s = _FakeSession()
    p = cli.build_payload(cli.RULE_LLM_JUDGE, name="r", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    cli.via_rest("create", payload=p, session=s)
    method, url, kw = s.calls[0]
    assert method == "POST"
    assert url.endswith("/v1/private/automations/evaluators/")
    assert kw["json"]["type"] == "llm_as_judge"
    assert kw["headers"]["Comet-Workspace"] is not None


def test_via_rest_delete_posts_ids():
    s = _FakeSession()
    cli.via_rest("delete", rule_id="abc", session=s)
    method, url, kw = s.calls[0]
    assert method == "POST"
    assert url.endswith("/v1/private/automations/evaluators/delete")
    assert kw["json"] == {"ids": ["abc"]}


def test_via_rest_get_uses_id_path_and_project_param():
    s = _FakeSession()
    cli.via_rest("get", rule_id="abc", project_id="pid", session=s)
    method, url, kw = s.calls[0]
    assert method == "GET"
    assert url.endswith("/v1/private/automations/evaluators/abc")
    assert kw["params"] == {"project_id": "pid"}


def test_build_sdk_request_returns_correct_variant():
    from opik.rest_api.types import AutomationRuleEvaluatorWrite_LlmAsJudge

    p = cli.build_payload(cli.RULE_LLM_JUDGE, name="r", project_id="pid",
                          sampling_rate=0.25, model="gpt-4o")
    req = cli.build_sdk_request(p)
    assert isinstance(req, AutomationRuleEvaluatorWrite_LlmAsJudge)
    assert req.name == "r"
    assert req.sampling_rate == 0.25
    # `schema` JSON alias maps to the typed `schema_` field:
    assert req.code.schema_[0].name == "relevance_score"


class _FakeEvaluators:
    def __init__(self):
        self.created = None

    def create_automation_rule_evaluator(self, *, request):
        self.created = request
        return None


class _FakeRestClient:
    def __init__(self):
        self.automation_rule_evaluators = _FakeEvaluators()


class _FakeClient:
    def __init__(self):
        self.rest_client = _FakeRestClient()


def test_via_sdk_create_calls_client_with_typed_request():
    from opik.rest_api.types import AutomationRuleEvaluatorWrite_TraceThreadLlmAsJudge

    client = _FakeClient()
    p = cli.build_payload(cli.RULE_THREAD_JUDGE, name="t", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    cli.via_sdk(client, "create", payload=p)
    sent = client.rest_client.automation_rule_evaluators.created
    assert isinstance(sent, AutomationRuleEvaluatorWrite_TraceThreadLlmAsJudge)
    assert sent.name == "t"


class _Page:
    def __init__(self, content):
        self.content = content


class _Proj:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class _FakeProjects:
    def __init__(self, existing=None):
        self._existing = list(existing or [])
        self.created_names = []

    def find_projects(self, *, name=None, **kw):
        return _Page([p for p in self._existing if p.name == name])

    def create_project(self, *, name, **kw):
        self.created_names.append(name)
        self._existing.append(_Proj("new-id", name))
        return None


class _ClientWithProjects:
    def __init__(self, projects):
        self.rest_client = type("R", (), {"projects": projects})()


def test_resolve_project_id_found():
    client = _ClientWithProjects(_FakeProjects([_Proj("pid-1", "demo")]))
    assert cli.resolve_project_id(client, "demo") == "pid-1"


def test_resolve_project_id_creates_when_missing():
    projects = _FakeProjects([])
    client = _ClientWithProjects(projects)
    assert cli.resolve_project_id(client, "demo") == "new-id"
    assert projects.created_names == ["demo"]


@pytest.mark.parametrize("argv_suffix", [
    ["create-llm-judge", "--name", "r", "--dry-run"],
    ["create-python",    "--name", "r", "--dry-run"],
    ["create-thread",    "--name", "r", "--dry-run"],
    ["create-span",      "--name", "r", "--dry-run"],
    ["create-span",      "--name", "r", "--dry-run", "--python"],
])
def test_main_dry_run_prints_sdk_and_curl(capsys, monkeypatch, argv_suffix):
    monkeypatch.setattr(sys, "argv", ["create-online-eval-rules"] + argv_suffix)
    importlib.reload(cli)
    rc = cli.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "── Python SDK ──" in out and "── REST (curl) ──" in out
