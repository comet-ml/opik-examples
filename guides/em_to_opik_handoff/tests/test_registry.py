import pytest

from roadwork_demo.config import HandoffError
from roadwork_demo.registry import (
    initial_status,
    next_version,
    pick_version,
    resolve_handoff,
    stock_handoff,
)


def test_first_version():
    assert next_version([]) == "1.0.0"


def test_bumps_major_of_highest():
    assert next_version(["1.0.0", "2.0.0"]) == "3.0.0"


def test_compares_numerically_not_as_text():
    assert next_version(["9.0.0", "10.0.0"]) == "11.0.0"


def test_ignores_unparseable_versions():
    assert next_version(["latest", "1.2.0"]) == "2.0.0"


def test_registered_version_found_for_this_model():
    from roadwork_demo.registry import registered_version

    assert registered_version("roadwork-yolo11s:2.0.0", "roadwork-yolo11s") == "2.0.0"


def test_registered_version_none_when_missing_or_other_model():
    from roadwork_demo.registry import registered_version

    assert registered_version(None, "roadwork-yolo11s") is None
    assert registered_version("", "roadwork-yolo11s") is None
    assert registered_version("other-model:1.0.0", "roadwork-yolo11s") is None


def test_fingerprint_dir_changes_with_content_not_with_order(tmp_path):
    from roadwork_demo.registry import fingerprint_dir

    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        (d / "sub").mkdir(parents=True)
    (a / "x.txt").write_text("1")
    (a / "sub" / "y.txt").write_text("2")
    (b / "sub" / "y.txt").write_text("2")
    (b / "x.txt").write_text("1")
    assert fingerprint_dir(a) == fingerprint_dir(b)
    (b / "x.txt").write_text("changed")
    assert fingerprint_dir(a) != fingerprint_dir(b)


def test_fingerprint_dir_sees_added_file(tmp_path):
    from roadwork_demo.registry import fingerprint_dir

    (tmp_path / "x.txt").write_text("1")
    before = fingerprint_dir(tmp_path)
    (tmp_path / "z.txt").write_text("")
    assert fingerprint_dir(tmp_path) != before


class FakeExperiment:
    url = "https://www.comet.com/ws/roadwork-detection/abc"

    def get_others_summary(self, other=None):
        return {"dataset_artifact": ["roadwork-yolo:1.0.0"]}.get(other, [])

    def get_metrics_summary(self, metric=None):
        summaries = {
            "metrics/mAP50(B)": {"name": "metrics/mAP50(B)", "valueCurrent": "0.41"},
            "metrics/mAP50-95(B)": {"name": "metrics/mAP50-95(B)", "valueCurrent": "0.22"},
        }
        return summaries.get(metric, [])


class FakeRegistryModel:
    def find_versions(self, version_prefix="", status=None, tag=None):
        return ["1.0.0"] if status == "Production" else ["2.0.0", "1.0.0"]

    def get_details(self, version):
        return {"experimentKey": "abc", "status": "Production" if version == "1.0.0" else "Staging"}


class FakeAPI:
    def __init__(self, experiment=None, model_error=None):
        self.experiment = experiment
        self.model_error = model_error
        self.model_requests = []

    def get_model(self, workspace, model_name):
        self.model_requests.append((workspace, model_name))
        if self.model_error:
            raise self.model_error
        return FakeRegistryModel()

    def get_experiment_by_key(self, key):
        return self.experiment


@pytest.fixture
def fake_api():
    return FakeAPI(experiment=FakeExperiment())


@pytest.fixture
def fake_api_missing_experiment():
    return FakeAPI(experiment=None)


def test_pick_explicit_version():
    assert pick_version("1.0.0", ["2.0.0", "1.0.0"], ["1.0.0"]) == "1.0.0"


def test_pick_unknown_version_lists_what_exists():
    with pytest.raises(HandoffError, match="2.0.0, 1.0.0"):
        pick_version("9.9.9", ["2.0.0", "1.0.0"], [])


def test_pick_production():
    assert pick_version("production", ["2.0.0", "1.0.0"], ["1.0.0"]) == "1.0.0"


def test_no_production_version_is_an_error_that_names_the_fix():
    with pytest.raises(HandoffError, match="--detector"):
        pick_version("production", ["2.0.0", "1.0.0"], [])


def test_first_registered_version_is_production_later_ones_staging():
    assert initial_status([]) == "Production"
    assert initial_status(["1.0.0"]) == "Staging"


def test_stock_handoff_identity():
    h = stock_handoff("ws", "roadwork-detection")
    assert h.model_tag() == "detector:yolo11s:stock" and h.experiment_key == ""


def test_resolve_handoff_reads_everything_from_the_registry(fake_api):
    h = resolve_handoff("ws", "roadwork-yolo11s", "production", "roadwork-detection", api=fake_api)
    assert (h.model_version, h.experiment_key, h.dataset_artifact) == ("1.0.0", "abc", "roadwork-yolo:1.0.0")
    assert h.experiment_url.endswith("/abc") and h.map50 == 0.41 and h.map50_95 == 0.22
    assert (h.comet_workspace, h.comet_project, h.registry_model) == (
        "ws",
        "roadwork-detection",
        "roadwork-yolo11s",
    )
    assert fake_api.model_requests == [("ws", "roadwork-yolo11s")]


def test_resolve_handoff_stock_needs_no_api():
    assert resolve_handoff("ws", "m", "stock", "p", api=None).model_version == "stock"


def test_deleted_source_experiment_is_a_handoff_error(fake_api_missing_experiment):
    with pytest.raises(HandoffError, match="abc"):
        resolve_handoff("ws", "roadwork-yolo11s", "1.0.0", "p", api=fake_api_missing_experiment)


def test_unreadable_registry_model_is_a_handoff_error_that_names_the_fix():
    api = FakeAPI(model_error=RuntimeError("404 model not found"))
    with pytest.raises(HandoffError, match="404 model not found.*03_register"):
        resolve_handoff("ws", "roadwork-yolo11s", "production", "p", api=api)
