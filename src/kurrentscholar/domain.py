from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from math import prod


class ConfidenceLabel(StrEnum):
    HIGHER = "higher"
    MODERATE = "moderate"
    HIGH_UNCERTAINTY = "high_uncertainty"
    VERY_HIGH_UNCERTAINTY = "very_high_uncertainty"
    UNAVAILABLE = "unavailable"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if min(self.x, self.y, self.width, self.height) < 0 or not self.width or not self.height:
            raise ValueError("Bounding box coordinates must be non-negative with positive dimensions")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class ConfidenceThresholds:
    higher: float = 0.90
    moderate: float = 0.75
    high_uncertainty: float = 0.50

    def __post_init__(self) -> None:
        if not 0 <= self.high_uncertainty <= self.moderate <= self.higher <= 1:
            raise ValueError("Confidence thresholds must be ordered within [0, 1]")

    def classify(self, score: float | None) -> ConfidenceLabel:
        if score is None:
            return ConfidenceLabel.UNAVAILABLE
        if score >= self.higher:
            return ConfidenceLabel.HIGHER
        if score >= self.moderate:
            return ConfidenceLabel.MODERATE
        if score >= self.high_uncertainty:
            return ConfidenceLabel.HIGH_UNCERTAINTY
        return ConfidenceLabel.VERY_HIGH_UNCERTAINTY


def geometric_mean(values: Iterable[float]) -> float | None:
    clean = [max(min(float(value), 1.0), 1e-12) for value in values]
    return prod(clean) ** (1 / len(clean)) if clean else None


@dataclass(slots=True)
class RecognitionResult:
    text: str
    token_ids: list[int]
    token_probabilities: list[float]
    line_confidence: float | None
    truncated: bool = False

