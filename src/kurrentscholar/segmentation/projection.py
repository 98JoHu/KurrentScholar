from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from kurrentscholar.domain import BoundingBox

from .base import DetectedLine


class ProjectionSegmenter:
    """Packageable fallback for mostly horizontal, single-column handwriting."""

    backend_id = "opencv-projection-fallback"
    version = "1"

    def __init__(self, minimum_height: int = 8, padding: int = 6) -> None:
        self.minimum_height = minimum_height
        self.padding = padding

    def detect_lines(self, image: Image.Image) -> list[DetectedLine]:
        gray = np.asarray(image.convert("L"))
        if gray.size == 0 or float(gray.std()) < 1.0:
            return []
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        width = binary.shape[1]
        kernel_width = max(15, width // 30)
        joined = cv2.morphologyEx(
            binary,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 3)),
        )
        occupied = np.count_nonzero(joined, axis=1) >= max(3, width // 300)
        bands = self._bands(occupied)
        boxes: list[BoundingBox] = []
        height, width = gray.shape
        for top, bottom in bands:
            if bottom - top < self.minimum_height:
                continue
            ys = slice(max(0, top - self.padding), min(height, bottom + self.padding))
            columns = np.flatnonzero(np.any(binary[ys, :] > 0, axis=0))
            if not len(columns):
                continue
            left = max(0, int(columns[0]) - self.padding)
            right = min(width, int(columns[-1]) + self.padding + 1)
            padded_top = max(0, top - self.padding)
            padded_bottom = min(height, bottom + self.padding)
            boxes.append(BoundingBox(left, padded_top, right - left, padded_bottom - padded_top))
        boxes.sort(key=lambda box: (box.y, box.x))
        return [DetectedLine(box, order) for order, box in enumerate(boxes)]

    @staticmethod
    def _bands(mask: np.ndarray) -> list[tuple[int, int]]:
        padded = np.pad(mask.astype(np.int8), (1, 1))
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        return list(zip(starts.tolist(), ends.tolist(), strict=True))

