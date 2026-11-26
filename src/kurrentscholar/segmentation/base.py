from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from kurrentscholar.domain import BoundingBox


@dataclass(frozen=True, slots=True)
class DetectedLine:
    bbox: BoundingBox
    reading_order: int
    crop: Image.Image | None = field(default=None, compare=False, repr=False)
    polygon: tuple[tuple[float, float], ...] = ()
