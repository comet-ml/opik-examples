"""Inter-rater agreement between two label sequences."""

from __future__ import annotations

from collections import Counter


def _check(a: list, b: list) -> None:
    if len(a) != len(b):
        raise ValueError(f"rating lists differ in length: {len(a)} vs {len(b)}")
    if not a:
        raise ValueError("no ratings to compare")


def percent_agreement(a: list, b: list) -> float:
    _check(a, b)
    return sum(x == y for x, y in zip(a, b)) / len(a)


def cohens_kappa(a: list, b: list) -> float:
    """Agreement corrected for chance. 1.0 perfect, 0.0 chance level."""
    _check(a, b)
    n = len(a)
    observed = percent_agreement(a, b)
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[label] * cb[label] for label in set(ca) | set(cb)) / (n * n)
    if expected == 1.0:
        # Both raters used one identical label throughout: agreement is total.
        return 1.0
    return (observed - expected) / (1 - expected)
