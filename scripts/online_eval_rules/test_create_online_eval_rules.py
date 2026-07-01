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
