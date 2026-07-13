from pathlib import Path

from conftest import write_entry


def test_write_entry_creates_valid_layout(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert (entry / "meta.yaml").is_file()
    assert (entry / "README.md").is_file()
    assert (entry / "opik-proof.png").is_file()


def test_write_entry_can_delete_a_meta_key(tmp_path: Path):
    import yaml

    entry = write_entry(tmp_path, meta={"title": None})
    data = yaml.safe_load((entry / "meta.yaml").read_text())
    assert "title" not in data
