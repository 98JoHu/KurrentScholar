from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from kurrentscholar.domain import BoundingBox


@dataclass(frozen=True, slots=True)
class DetectedLine:
    bbox: BoundingBox
    reading_order: int


class SegmentationBackend(Protocol):
    backend_id: str
    version: str

    def detect_lines(self, image: Image.Image) -> list[DetectedLine]: ...

