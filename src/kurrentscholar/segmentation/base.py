from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image

from kurrentscholar.domain import BoundingBox


@dataclass(frozen=True, slots=True)
class DetectedLine:
    bbox: BoundingBox
    reading_order: int
    crop: Image.Image | None = field(default=None, compare=False, repr=False)
    polygon: tuple[tuple[float, float], ...] = ()


class SegmentationBackend(Protocol):
    backend_id: str
    version: str

    def detect_lines(self, image: Image.Image) -> list[DetectedLine]: ...

