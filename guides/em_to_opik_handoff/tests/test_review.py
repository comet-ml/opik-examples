from roadwork_demo.review import top_up


def test_top_up_fills_an_empty_queue_to_the_target():
    assert top_up(["a", "b", "c"], queued=set(), eligible={"a", "b", "c"}, target=3) == ["a", "b", "c"]


def test_top_up_adds_only_what_is_missing():
    # Queue already holds 2 traces of this version; a fresh sample of 3 must add 1, not 3.
    eligible = {"a", "b", "c", "d", "e"}
    assert top_up(["c", "d", "e"], queued={"a", "b"}, eligible=eligible, target=3) == ["c"]


def test_top_up_skips_traces_already_queued():
    assert top_up(["a", "c"], queued={"a"}, eligible={"a", "c"}, target=3) == ["c"]


def test_top_up_adds_nothing_when_queue_is_full():
    eligible = {"a", "b", "c", "d", "x"}
    assert top_up(["c", "d"], queued={"a", "b", "x"}, eligible=eligible, target=3) == []


def test_top_up_does_not_count_queued_traces_of_another_detector_version():
    # WHY: after a promote the queue is full of the old version's traces; the new Production
    # version must still get its own sample.
    assert top_up(["c", "d"], queued={"a", "b", "x"}, eligible={"c", "d"}, target=2) == ["c", "d"]
