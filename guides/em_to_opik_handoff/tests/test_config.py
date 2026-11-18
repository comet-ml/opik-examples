import os

import pytest

from roadwork_demo.config import (
    Handoff,
    exit_if_dry_run,
    exit_if_no_comet,
    experiment_name,
    get_settings,
    is_dev_experiment,
    is_full_run,
    should_link_back,
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
        0.5,
        0.3,
    )


def test_model_tag_and_metadata(h):
    assert h.model_tag() == "detector:roadwork-yolo11s:1.0.0"
    md = h.as_metadata()
    assert md["em_url"] == h.experiment_url and md["model_version"] == "1.0.0"
    assert not hasattr(h, "classes")


def test_defaults(monkeypatch):
    for k in (
        "OPIK_PROJECT_NAME",
        "OPIK_EXAMPLES_MODEL",
        "JUDGE_MODEL",
        "OPIK_ONLINE_JUDGE_MODEL",
        "DETECTOR_VERSION",
        "OPIK_DATASET",
    ):
        monkeypatch.delenv(k, raising=False)
    s = get_settings()
    assert s.project == "roadwork-detection"
    assert s.opik_dataset == "roadwork-verdicts" and s.dev_dataset == "roadwork-verdicts-dev"
    assert s.verdict_model == "anthropic/claude-haiku-5-5"
    assert s.judge_model == "anthropic/claude-sonnet-5-5"
    assert s.online_judge_model == "opik-free-model"
    assert s.detector == "production"


def test_empty_env_value_falls_back(monkeypatch):
    # WHY: an unset GitHub Actions variable arrives as "".
    monkeypatch.setenv("OPIK_EXAMPLES_MODEL", "")
    assert get_settings().verdict_model == "anthropic/claude-haiku-5-5"


def test_project_is_exported_for_the_opik_sdk(monkeypatch):
    monkeypatch.setenv("OPIK_PROJECT_NAME", "roadwork-detection-dev")
    assert get_settings().project == os.environ["OPIK_PROJECT_NAME"] == "roadwork-detection-dev"


def test_one_workspace_for_both_products(monkeypatch):
    monkeypatch.delenv("COMET_WORKSPACE", raising=False)
    monkeypatch.setenv("OPIK_WORKSPACE", "opik-examples")
    assert get_settings().workspace == "opik-examples"


def test_dry_run_without_opik_credentials(monkeypatch):
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    assert get_settings().dry_run is True


def test_experiment_names():
    assert experiment_name("vlm_only", None) == "vlm_only"
    # WHY: no detector ran, so the detector version is not part of the name.
    assert experiment_name("vlm_only", "1.0.0") == "vlm_only"
    assert experiment_name("detector_vlm", "1.0.0") == "detector_vlm-1.0.0"
    assert experiment_name("detector_vlm", "stock") == "detector_vlm-stock"
    assert experiment_name("detector_vlm", "2.0.0", full_run=False) == "detector_vlm-2.0.0-dev"


def test_full_run_means_every_item_of_the_default_dataset():
    assert is_full_run("d", "d", None) is True
    assert is_full_run("d", "d", 5) is False
    assert is_full_run("d-dev", "d", None) is False


def test_link_back_only_for_full_run_on_registered_model():
    assert should_link_back("1.0.0", full_run=True) is True
    assert should_link_back("stock", full_run=True) is False
    assert should_link_back("1.0.0", full_run=False) is False


def test_dev_experiments_are_recognised_by_name_and_stock_is_not_one():
    assert is_dev_experiment("vlm_only-dev") is True
    assert is_dev_experiment("detector_vlm-2.0.0-dev") is True
    assert is_dev_experiment("detector_vlm-stock-dev") is True
    assert is_dev_experiment("detector_vlm-stock") is False
    assert is_dev_experiment("detector_vlm-1.0.0") is False
    assert is_dev_experiment("vlm_only") is False
    assert is_dev_experiment("someone-elses-experiment-dev") is False


def test_scripts_stop_cleanly_without_opik_credentials(monkeypatch, capsys):
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    with pytest.raises(SystemExit) as stop:
        exit_if_dry_run(get_settings(), "run the experiments")
    assert stop.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("[DRY RUN]") and "run the experiments" in out and "OPIK_API_KEY" in out


def test_scripts_continue_with_opik_credentials(monkeypatch):
    monkeypatch.setenv("OPIK_API_KEY", "k")
    monkeypatch.setenv("OPIK_WORKSPACE", "ws")
    assert exit_if_dry_run(get_settings(), "run the experiments") is None


def test_comet_scripts_stop_cleanly_without_comet_credentials(monkeypatch, capsys):
    monkeypatch.delenv("COMET_API_KEY", raising=False)
    monkeypatch.setenv("COMET_WORKSPACE", "ws")
    with pytest.raises(SystemExit) as stop:
        exit_if_no_comet(get_settings(), "train the detector")
    assert stop.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("[DRY RUN]") and "train the detector" in out and "COMET_API_KEY" in out


def test_comet_scripts_stop_cleanly_without_a_workspace(monkeypatch):
    monkeypatch.setenv("COMET_API_KEY", "k")
    monkeypatch.delenv("COMET_WORKSPACE", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)
    with pytest.raises(SystemExit) as stop:
        exit_if_no_comet(get_settings(), "train the detector")
    assert stop.value.code == 0


def test_comet_scripts_continue_with_comet_credentials(monkeypatch):
    monkeypatch.setenv("COMET_API_KEY", "k")
    monkeypatch.setenv("COMET_WORKSPACE", "ws")
    assert exit_if_no_comet(get_settings(), "train the detector") is None
