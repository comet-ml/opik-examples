from roadwork_demo.review import top_up


def test_top_up_fills_an_empty_queue_to_the_target():
    assert top_up(["a", "b", "c"], already=set(), target=3) == ["a", "b", "c"]


def test_top_up_adds_only_what_is_missing():
    # Queue already holds 2 traces; a fresh sample of 3 must add 1, not 3.
    assert top_up(["c", "d", "e"], already={"a", "b"}, target=3) == ["c"]


def test_top_up_skips_traces_already_queued():
    assert top_up(["a", "c"], already={"a"}, target=3) == ["c"]


def test_top_up_adds_nothing_when_queue_is_full():
    assert top_up(["c", "d"], already={"a", "b", "x"}, target=3) == []
