import json

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


def test_render_sdk_snippet_names_variant():
    p = cli.build_payload(cli.RULE_SPAN_PY, name="r", project_id="pid",
                          sampling_rate=1.0, model="gpt-4o")
    out = cli.render_sdk_snippet(p)
    assert "AutomationRuleEvaluatorWrite_SpanUserDefinedMetricPython" in out
    assert "create_automation_rule_evaluator" in out


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
