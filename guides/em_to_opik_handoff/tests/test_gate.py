from types import SimpleNamespace

from roadwork_demo.gate import decide, latest


def test_promote_when_better():
    assert decide(0.80, 0.75) == "promote"


def test_hold_on_tie():
    assert decide(0.75, 0.75) == "hold"


def test_hold_when_gain_below_min_delta():
    assert decide(0.76, 0.75, min_delta=0.02) == "hold"


def test_hold_when_worse():
    assert decide(0.70, 0.75) == "hold"


def test_latest_picks_the_newest_of_same_named_experiments():
    # Opik ids are time-ordered (UUID v7), so the highest id is the most recent run.
    old = SimpleNamespace(id="01a1-0001", name="vlm_only-1.0.0")
    new = SimpleNamespace(id="01a1-0002", name="vlm_only-1.0.0")
    assert latest([new, old], "vlm_only-1.0.0") is new
    assert latest([old], "vlm_only-1.0.0") is old


def test_latest_ignores_experiments_that_only_share_a_prefix():
    # Opik's lookup by name also returns "vlm_only-1.0.0-dev" for "vlm_only-1.0.0".
    full = SimpleNamespace(id="01a1-0001", name="vlm_only-1.0.0")
    dev = SimpleNamespace(id="01a1-0009", name="vlm_only-1.0.0-dev")
    assert latest([dev, full], "vlm_only-1.0.0") is full
    assert latest([dev], "vlm_only-1.0.0") is None
