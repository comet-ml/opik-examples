from roadwork_demo.registry import next_version


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
