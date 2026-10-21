"""Tests for the Opik access layer, using stub clients (no network)."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

import opik_access
from opik_access import ConfigError, GitContext


def test_git_context_prefers_head_ref_and_parses_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_HEAD_REF", "feat/x")
    monkeypatch.setenv("GITHUB_REF_NAME", "42/merge")
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234")
    monkeypatch.setenv("GITHUB_ACTOR", "octocat")
    ctx = opik_access.git_context()
    assert ctx.branch == "feat/x"
    assert ctx.pr_number == "42"
    assert ctx.sha7 == "abcdef1"
    assert ctx.actor == "octocat"
    assert opik_access.git_context(pr_override="7").pr_number == "7"


def test_experiment_name_replaces_slash() -> None:
    ctx = GitContext(branch="feat/x", sha7="abcdef1", pr_number=None, actor=None)
    assert opik_access.experiment_name(ctx) == "feat-x-abcdef1"


def test_find_baseline_skips_excluded_id() -> None:
    calls: list[dict[str, Any]] = []

    def find_experiments(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            content=[
                SimpleNamespace(id="cand", tags=["ci", "baseline"]),
                SimpleNamespace(id="base", tags=["ci", "baseline"]),
            ]
        )

    client = SimpleNamespace(
        rest_client=SimpleNamespace(experiments=SimpleNamespace(find_experiments=find_experiments))
    )
    found = opik_access.find_baseline(client, "ds1", exclude_id="cand")
    assert found is not None and found.id == "base"
    assert calls[0]["dataset_id"] == "ds1"
    assert json.loads(calls[0]["filters"])[0]["value"] == "baseline"
    assert calls[0]["size"] == 20
    assert opik_access.find_baseline(client, "ds1", exclude_id=None).id == "cand"  # type: ignore[union-attr]


def test_ui_base_and_workspace_resolves_default() -> None:
    client = SimpleNamespace(
        config=SimpleNamespace(url_override="https://host.example.com/opik/api", workspace="default"),
        rest_client=SimpleNamespace(
            check=SimpleNamespace(get_workspace_name=lambda: SimpleNamespace(workspace_name="acme"))
        ),
    )
    base, ws = opik_access.ui_base_and_workspace(client)
    assert base == "https://host.example.com/"
    assert ws == "acme"
    client.config.workspace = "team"
    assert opik_access.ui_base_and_workspace(client)[1] == "team"


def test_fetch_compare_rows_pages_until_total() -> None:
    calls: list[int] = []

    def find(**kwargs: Any) -> SimpleNamespace:
        page = kwargs["page"]
        calls.append(page)
        n = 100 if page < 3 else 50
        return SimpleNamespace(content=[object()] * n, page=page, size=kwargs["size"], total=250)

    client = SimpleNamespace(
        rest_client=SimpleNamespace(datasets=SimpleNamespace(find_dataset_items_with_experiment_items=find))
    )
    rows = opik_access.fetch_compare_rows(client, "ds1", ["e1", "e2"])
    assert len(rows) == 250
    assert calls == [1, 2, 3]


def test_load_callable_bad_ref_raises_config_error() -> None:
    for ref in ("nocolon", "no_such_module_xyz:fn", "json:no_such_attr"):
        with pytest.raises(ConfigError) as exc:
            opik_access.load_callable(ref)
        assert ref in str(exc.value)
    assert opik_access.load_callable("json:dumps") is json.dumps


def test_resolve_experiment_falls_back_without_project() -> None:
    import opik.exceptions

    match = SimpleNamespace(name="exp", created_at=1)
    match.get_experiment_data = lambda: match  # type: ignore[attr-defined]
    seen: list[Any] = []

    def get_by_name(name: str, project_name: str | None = None) -> list[Any]:
        seen.append(project_name)
        if project_name is not None:
            raise opik.exceptions.ExperimentNotFound(name)
        return [match]

    def by_id(_: str) -> Any:
        raise RuntimeError("not an id")

    client = SimpleNamespace(
        get_experiments_by_name=get_by_name,
        rest_client=SimpleNamespace(experiments=SimpleNamespace(get_experiment_by_id=by_id)),
    )
    assert opik_access.resolve_experiment(client, "exp", "proj") is match
    assert seen == ["proj", None]


def test_find_baseline_requires_exact_tag_not_substring() -> None:
    newer = SimpleNamespace(id="new", tags=["ci", "fix-baseline-loader", "candidate"])
    older = SimpleNamespace(id="old", tags=["ci", "main", "baseline"])
    client = SimpleNamespace(
        rest_client=SimpleNamespace(
            experiments=SimpleNamespace(find_experiments=lambda **_k: SimpleNamespace(content=[newer, older]))
        )
    )
    found = opik_access.find_baseline(client, "ds1")
    assert found is not None and found.id == "old"


def test_mark_baseline_adds_tag_by_id() -> None:
    calls: list[dict[str, Any]] = []
    client = SimpleNamespace(
        rest_client=SimpleNamespace(
            experiments=SimpleNamespace(update_experiment=lambda **kw: calls.append(kw))
        )
    )
    opik_access.mark_baseline(client, "exp1")
    assert calls == [{"id": "exp1", "tags_to_add": ["baseline"]}]


def test_git_context_prefers_eval_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPIK_EVAL_GIT_SHA", "abcdef1234")
    monkeypatch.setenv("GITHUB_SHA", "zzzzzzz999")
    assert opik_access.git_context().sha7 == "abcdef1"
    monkeypatch.delenv("OPIK_EVAL_GIT_SHA")
    assert opik_access.git_context().sha7 == "zzzzzzz"


def test_server_version_unwraps_version_key() -> None:
    def make(value: Any) -> SimpleNamespace:
        return SimpleNamespace(rest_client=SimpleNamespace(version=lambda: value))

    assert opik_access.server_version(make({"version": "2.2.113"})) == "2.2.113"
    assert opik_access.server_version(make("2.2.9")) == "2.2.9"
