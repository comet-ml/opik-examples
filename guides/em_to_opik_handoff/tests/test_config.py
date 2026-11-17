import pytest

from roadwork_demo.config import (
    Handoff,
    HandoffError,
    get_settings,
    load_handoff,
    save_handoff,
)


@pytest.fixture
def h():
    return Handoff(
        "ws",
        "roadwork-detector",
        "abc123",
        "https://www.comet.com/ws/roadwork-detector/abc123",
        "roadwork-yolo11s",
        "1.0.0",
        "roadwork-yolo:1.0.0",
        ["Cone"],
        0.5,
        0.3,
    )


def test_handoff_roundtrip(tmp_path, h):
    save_handoff(h, tmp_path / "handoff.json")
    assert load_handoff(tmp_path / "handoff.json") == h


def test_model_tag_and_metadata(h):
    assert h.model_tag() == "detector:roadwork-yolo11s:1.0.0"
    md = h.as_metadata()
    assert md["em_url"] == h.experiment_url and "classes" not in md


def test_missing_file_names_the_fix(tmp_path):
    with pytest.raises(HandoffError, match="03_register"):
        load_handoff(tmp_path / "nope.json")


def test_missing_field_is_named(tmp_path):
    (tmp_path / "h.json").write_text('{"comet_workspace": "ws"}')
    with pytest.raises(HandoffError, match="experiment_key"):
        load_handoff(tmp_path / "h.json")


@pytest.fixture
def no_dotenv(monkeypatch):
    """Keep the developer's real .env out of the settings tests."""
    monkeypatch.setattr("roadwork_demo.config.load_dotenv", lambda *a, **k: False)


def test_settings_defaults(monkeypatch, no_dotenv):
    monkeypatch.delenv("OPIK_PROJECT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_URL", raising=False)
    s = get_settings()
    assert s.opik_project == "roadwork-triage"
    assert s.anthropic_api_url == "https://api.anthropic.com"


def test_settings_pin_opik_default_project(monkeypatch, no_dotenv):
    import os

    monkeypatch.setenv("OPIK_PROJECT_NAME", "someone-elses-project")
    monkeypatch.delenv("OPIK_PROJECT", raising=False)
    s = get_settings()
    assert os.environ["OPIK_PROJECT_NAME"] == s.opik_project == "roadwork-triage"


def test_link_back_only_for_full_run_on_registered_model():
    from roadwork_demo.config import should_link_back

    full = dict(dataset_name="roadwork-verdicts-v1", default_dataset="roadwork-verdicts-v1", nb_samples=None)
    assert should_link_back(model_version="1.0.0", **full) is True
    assert should_link_back(model_version="dev-stock", **full) is False
    assert should_link_back(model_version="1.0.0", **(full | {"nb_samples": 5})) is False
    assert (
        should_link_back(model_version="1.0.0", **(full | {"dataset_name": "roadwork-verdicts-v1-dev"}))
        is False
    )


def test_partial_runs_get_their_own_experiment_name():
    from roadwork_demo.config import experiment_name, is_full_run

    assert experiment_name("vlm_only", "1.0.0") == "vlm_only-1.0.0"
    assert experiment_name("vlm_only", "1.0.0", full_run=False) == "vlm_only-1.0.0-dev"
    assert is_full_run("d", "d", None) is True
    assert is_full_run("d", "d", 5) is False
    assert is_full_run("d-dev", "d", None) is False
