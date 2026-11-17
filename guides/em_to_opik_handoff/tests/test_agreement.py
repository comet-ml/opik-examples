import pytest

from roadwork_demo.agreement import cohens_kappa, percent_agreement


def test_percent_agreement():
    assert percent_agreement(["a", "b", "a", "a"], ["a", "b", "b", "a"]) == 0.75


def test_kappa_perfect():
    assert cohens_kappa([0, 1, 0, 1], [0, 1, 0, 1]) == pytest.approx(1.0)


def test_kappa_known_value():
    a = [1, 1, 0, 0, 1, 0, 1, 1, 0, 0]
    b = [1, 0, 0, 0, 1, 0, 1, 1, 1, 0]
    assert cohens_kappa(a, b) == pytest.approx(0.6)


def test_kappa_chance():
    assert cohens_kappa([0, 0, 1, 1], [0, 1, 0, 1]) == pytest.approx(0.0)


def test_kappa_single_label():
    assert cohens_kappa(["a", "a"], ["a", "a"]) == 1.0


def test_mismatch_raises():
    with pytest.raises(ValueError):
        percent_agreement([1], [1, 2])
    with pytest.raises(ValueError):
        cohens_kappa([], [])
