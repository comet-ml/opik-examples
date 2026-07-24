import importlib

import pytest


def _reload_config(monkeypatch, **env):
    env_vars = [
        "OPIK_API_KEY",
        "OPIK_WORKSPACE",
        "OPIK_EXAMPLES_MODEL",
        "OPIK_PROJECT_NAME",
        "ANTHROPIC_API_KEY",
    ]
    for k in env_vars:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import optimization_guide.config as config
    return importlib.reload(config)


def test_default_model_when_unset(monkeypatch):
    config = _reload_config(monkeypatch)
    assert config.GEN_MODEL == "anthropic/claude-sonnet-4-6"
    assert config.JUDGE_MODEL == "anthropic/claude-sonnet-4-6"
    assert config.OPTIMIZER_MODEL == "anthropic/claude-sonnet-4-6"


def test_model_override(monkeypatch):
    config = _reload_config(monkeypatch, OPIK_EXAMPLES_MODEL="openai/gpt-4o-mini")
    assert config.GEN_MODEL == "openai/gpt-4o-mini"


def test_project_name_default(monkeypatch):
    config = _reload_config(monkeypatch)
    assert config.PROJECT_NAME == "prompt-agent-optimization"


def test_check_prerequisites_raises_when_missing(monkeypatch):
    config = _reload_config(monkeypatch)  # no OPIK_API_KEY / OPIK_WORKSPACE
    with pytest.raises(RuntimeError) as exc:
        config.check_prerequisites()
    assert "OPIK_API_KEY" in str(exc.value)
    assert "OPIK_WORKSPACE" in str(exc.value)


def test_check_prerequisites_passes_when_present(monkeypatch):
    config = _reload_config(monkeypatch, OPIK_API_KEY="x", OPIK_WORKSPACE="w", ANTHROPIC_API_KEY="k")
    assert config.check_prerequisites() is None
