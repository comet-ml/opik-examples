import json
from collections import Counter

import pytest
from PIL import Image

from roadwork_demo.data import (
    VERDICTS,
    coco_bbox_to_yolo,
    convert_split,
    select_eval_frames,
)


def test_verdict_labels():
    assert VERDICTS == ("blocked", "partial", "clear")


def test_bbox_center_normalized():
    assert coco_bbox_to_yolo([100, 200, 50, 100], 1000, 1000) == pytest.approx((0.125, 0.25, 0.05, 0.1))


def test_bbox_clipped_to_image():
    cx, cy, w, h = coco_bbox_to_yolo([950, 0, 100, 100], 1000, 1000)
    assert cx + w / 2 <= 1.0 and w == pytest.approx(0.05)


def test_bbox_zero_area_dropped():
    assert coco_bbox_to_yolo([1000, 10, 50, 50], 1000, 1000) is None
    assert coco_bbox_to_yolo([10, 10, 0, 50], 1000, 1000) is None


def _img(name, tags, desc=None):
    return {
        "file_name": name,
        "scene_level_tags": {"travel_alteration": tags},
        "scene_description": desc if desc is not None else f"desc {name}",
        "city_name": "pittsburgh",
    }


@pytest.mark.parametrize(
    "desc,expected",
    [
        ("Road closed and fully blocked by barricades and cones.", True),
        ("Sidewalk partially blocked by TTC signs. Road fully blocked by fence.", True),
        ("Cones fully blocking road. TTC message board off road.", True),
        ("Right intersecting road fully blocked by line of cones.", False),
        ("Left sidewalk closed and fully blocked by barricades.", False),
        ("Right lane fully blocked by work vehicle.", False),
        ("Cones on left side of road.", False),
        ("", False),
        ("No Description", False),
    ],
)
def test_describes_own_road_closed(desc, expected):
    from roadwork_demo.data import describes_own_road_closed

    assert describes_own_road_closed(desc) is expected


ROAD_CLOSED = "Road closed and fully blocked by barricades."
SIDEWALK = "Left sidewalk closed and fully blocked by barricades."


def test_select_eval_frames_prefers_pure_blocked_and_is_deterministic():
    images = (
        [_img(f"pure_fb_{i}", ["Fully Blocked"], ROAD_CLOSED) for i in range(3)]
        + [_img(f"mixed_{i}", ["Fully Blocked", "Partially Blocked"], ROAD_CLOSED) for i in range(5)]
        + [_img(f"pb_{i}", ["Partially Blocked"]) for i in range(10)]
        + [_img(f"ls_{i}", ["Lane Shift", "Partially Blocked"]) for i in range(4)]
        + [_img(f"none_{i}", ["None"]) for i in range(2)]
        + [_img("other_0", ["Other"])]
    )
    out = select_eval_frames(images, per_class=4, seed=7)
    counts = Counter(i["verdict"] for i in out)
    assert counts == {"blocked": 4, "partial": 4, "clear": 2}
    names = {i["file_name"] for i in out}
    assert {"pure_fb_0", "pure_fb_1", "pure_fb_2"} <= names
    assert not any(n.startswith("ls_") for n in names)
    assert set(out[0]) == {"file_name", "verdict", "scene_description", "city_name"}
    assert out == select_eval_frames(images, per_class=4, seed=7)


def test_select_eval_frames_skips_blocked_tags_that_are_not_about_the_road():
    images = [
        _img("sidewalk_0", ["Fully Blocked"], SIDEWALK),
        _img("side_road_0", ["Fully Blocked"], "Right intersecting road fully blocked by cones."),
        _img("road_0", ["Fully Blocked", "Partially Blocked"], ROAD_CLOSED),
    ]
    out = select_eval_frames(images, per_class=5, seed=7)
    assert [i["file_name"] for i in out if i["verdict"] == "blocked"] == ["road_0"]


def test_convert_split_writes_labels(tmp_path):
    img = tmp_path / "src" / "a.jpg"
    img.parent.mkdir()
    Image.new("RGB", (1000, 1000)).save(img)
    coco = {
        "images": [{"id": 1, "file_name": "a.jpg", "width": 1000, "height": 1000}],
        "annotations": [
            {"image_id": 1, "category_id": 3, "bbox": [100, 200, 50, 100]},
            {"image_id": 1, "category_id": 5, "bbox": [10, 10, 0, 50]},
        ],
        "categories": [{"id": 3, "name": "Cone"}, {"id": 5, "name": "Drum"}],
    }
    coco_json = tmp_path / "coco.json"
    coco_json.write_text(json.dumps(coco))
    n = convert_split(coco_json, {"a.jpg": img}, tmp_path / "yolo", "train")
    assert n == 1
    lines = (tmp_path / "yolo/labels/train/a.txt").read_text().splitlines()
    assert len(lines) == 1
    # Class index is the position in data.yaml (categories sorted by id), not id - 1.
    assert lines[0].split()[0] == "0"
    assert (tmp_path / "yolo/images/train/a.jpg").exists()


def test_convert_split_skips_images_missing_on_disk(tmp_path):
    coco = {
        "images": [{"id": 1, "file_name": "gone.jpg", "width": 10, "height": 10}],
        "annotations": [],
        "categories": [],
    }
    coco_json = tmp_path / "coco.json"
    coco_json.write_text(json.dumps(coco))
    assert convert_split(coco_json, {}, tmp_path / "yolo", "val") == 0


def test_image_index_matches_extension_case_insensitively(tmp_path):
    from roadwork_demo.data import build_image_index, find_image

    (tmp_path / "sub").mkdir()
    Image.new("RGB", (10, 10)).save(tmp_path / "sub" / "pgh04_0001.JPG", format="JPEG")
    Image.new("RGB", (10, 10)).save(tmp_path / "boston_1.jpg")
    (tmp_path / "notes.txt").write_text("x")
    index = build_image_index(tmp_path)
    assert len(index) == 2
    assert find_image(index, "pgh04_0001.jpg") == tmp_path / "sub" / "pgh04_0001.JPG"
    assert find_image(index, "PGH04_0001.JPG") is not None
    assert find_image(index, "missing.jpg") is None


def test_convert_split_finds_uppercase_extension(tmp_path):
    from roadwork_demo.data import build_image_index

    src = tmp_path / "src"
    src.mkdir()
    Image.new("RGB", (100, 100)).save(src / "pgh.JPG", format="JPEG")
    coco = {
        "images": [{"id": 1, "file_name": "pgh.jpg", "width": 100, "height": 100}],
        "annotations": [{"image_id": 1, "category_id": 1, "bbox": [10, 10, 20, 20]}],
        "categories": [{"id": 1, "name": "Cone"}],
    }
    coco_json = tmp_path / "coco.json"
    coco_json.write_text(json.dumps(coco))
    assert convert_split(coco_json, build_image_index(src), tmp_path / "yolo", "train") == 1
    assert (tmp_path / "yolo/labels/train/pgh.txt").exists()


def test_convert_split_removes_files_from_a_previous_larger_run(tmp_path):
    from roadwork_demo.data import build_image_index

    src = tmp_path / "src"
    src.mkdir()
    images = []
    for i in range(4):
        Image.new("RGB", (50, 50)).save(src / f"f{i}.jpg")
        images.append({"id": i, "file_name": f"f{i}.jpg", "width": 50, "height": 50})
    coco_json = tmp_path / "coco.json"
    coco_json.write_text(json.dumps({"images": images, "annotations": [], "categories": []}))
    index = build_image_index(src)
    assert convert_split(coco_json, index, tmp_path / "yolo", "train") == 4
    assert convert_split(coco_json, index, tmp_path / "yolo", "train", max_images=2) == 2
    assert len(list((tmp_path / "yolo/images/train").iterdir())) == 2
    assert len(list((tmp_path / "yolo/labels/train").iterdir())) == 2


def test_stale_item_ids_finds_removed_and_relabelled_items():
    from roadwork_demo.data import stale_item_ids

    manifest = [
        {"file_name": "a.jpg", "verdict": "blocked"},
        {"file_name": "b.jpg", "verdict": "clear"},
    ]
    existing = [
        {"id": "1", "file_name": "a.jpg", "expected_verdict": "blocked"},  # still wanted
        {"id": "2", "file_name": "b.jpg", "expected_verdict": "partial"},  # label changed
        {"id": "3", "file_name": "gone.jpg", "expected_verdict": "clear"},  # left the manifest
    ]
    assert stale_item_ids(existing, manifest) == ["2", "3"]


def test_data_yaml_for_the_artifact_carries_no_local_path(tmp_path):
    from roadwork_demo.data import portable_data_yaml, write_data_yaml

    local = write_data_yaml(tmp_path, ["Cone", "Drum"]).read_text()
    assert str(tmp_path.resolve()) in local
    portable = portable_data_yaml(local)
    assert str(tmp_path.resolve()) not in portable
    assert portable.splitlines()[0] == "path: ."
    assert portable.splitlines()[1:] == local.splitlines()[1:]
