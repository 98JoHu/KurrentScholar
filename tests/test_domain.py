import pytest

from kurrentscholar.domain import ConfidenceLabel, ConfidenceThresholds, geometric_mean


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (None, ConfidenceLabel.UNAVAILABLE),
        (0.9, ConfidenceLabel.HIGHER),
        (0.8999, ConfidenceLabel.MODERATE),
        (0.75, ConfidenceLabel.MODERATE),
        (0.7499, ConfidenceLabel.HIGH_UNCERTAINTY),
        (0.5, ConfidenceLabel.HIGH_UNCERTAINTY),
        (0.4999, ConfidenceLabel.VERY_HIGH_UNCERTAINTY),
    ],
)
def test_confidence_boundaries(score, label):
    assert ConfidenceThresholds().classify(score) == label


def test_geometric_mean():
    assert geometric_mean([0.25, 1.0]) == pytest.approx(0.5)
    assert geometric_mean([]) is None

