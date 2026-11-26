from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from kurrentscholar.domain import BoundingBox

from .base import DetectedLine


def deskew_matrix(width: int, height: int, angle: float) -> np.ndarray:
    """Affine transform that rotates a page about its centre by the stored deskew angle."""

    return cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)


def deskew_image(image: Image.Image, angle: float) -> Image.Image:
    """Rotate a page exactly as line detection does before cropping lines for recognition."""

    rgb = image.convert("RGB")
    if not angle:
        return rgb
    return Image.fromarray(
        cv2.warpAffine(
            np.asarray(rgb),
            deskew_matrix(rgb.width, rgb.height, angle),
            (rgb.width, rgb.height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
    )


def recognition_crop(
    deskewed: Image.Image,
    polygon: list[tuple[float, float]],
    angle: float,
) -> Image.Image:
    """Recreate the horizontal line crop given to the recognizer from stored source geometry.

    ``polygon`` is the line outline on the unrotated page; mapping it forward with the page's
    deskew transform yields the axis-aligned box that was cropped from the deskewed page.
    """

    points = np.array([[x, y, 1.0] for x, y in polygon], dtype=np.float64)
    mapped = points @ deskew_matrix(deskewed.width, deskewed.height, angle).T
    left = max(0, int(round(mapped[:, 0].min())))
    top = max(0, int(round(mapped[:, 1].min())))
    right = min(deskewed.width, int(round(mapped[:, 0].max())))
    bottom = min(deskewed.height, int(round(mapped[:, 1].max())))
    return deskewed.crop((left, top, max(left + 1, right), max(top + 1, bottom)))


class ProjectionSegmenter:
    """Detect handwriting lines using ink-density peaks and separating valleys.

    Historical handwriting regularly has descenders, flourishes, brackets, and
    underlining that connect adjacent lines. Treating every connected horizontal
    band as a line therefore produces multi-line blocks. This detector locates the
    centre of each line independently and assigns it the valley between neighbouring
    centres, so those connections do not merge the lines.
    """

    backend_id = "opencv-projection-fallback"
    version = "3"

    def __init__(self, minimum_height: int = 8, padding: int = 6) -> None:
        self.minimum_height = minimum_height
        self.padding = padding
        self.last_deskew_angle = 0.0

    def detect_lines(self, image: Image.Image) -> list[DetectedLine]:
        self.last_deskew_angle = 0.0
        gray = np.asarray(image.convert("L"))
        if gray.size == 0 or float(gray.std()) < 1.0:
            return []

        otsu_threshold = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )[0]
        # Yellowed paper, shadows, and reverse-side bleed-through can make Otsu's
        # threshold so light that the paper itself becomes "ink". Genuine ink in
        # the supported scans remains comfortably below this conservative cap.
        ink_threshold = min(float(otsu_threshold), 190.0)
        binary = cv2.threshold(gray, ink_threshold, 255, cv2.THRESH_BINARY_INV)[1]
        height, width = binary.shape
        analysis = binary.copy()
        self._clear_scan_edges(analysis)

        self.last_deskew_angle = self._estimate_deskew_angle(analysis)
        matrix: np.ndarray | None = None
        deskewed_image = image.convert("RGB")
        if self.last_deskew_angle:
            matrix = deskew_matrix(width, height, self.last_deskew_angle)
            analysis = cv2.warpAffine(
                analysis,
                matrix,
                (width, height),
                flags=cv2.INTER_NEAREST,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            self._clear_scan_edges(analysis)
            deskewed_image = deskew_image(deskewed_image, self.last_deskew_angle)

        profile = np.count_nonzero(analysis, axis=1).astype(np.float32)
        smooth_profile = self._smooth(profile, height)
        centres = self._line_centres(smooth_profile, width, height)
        if not centres:
            return []

        boundaries = self._valley_boundaries(smooth_profile, centres, height)
        boxes: list[BoundingBox] = []
        for centre, (top, bottom) in zip(centres, boundaries, strict=True):
            boxes.extend(self._boxes_in_band(analysis, top, bottom, centre))

        boxes = self._remove_implausibly_tall_boxes(boxes, height)
        boxes.sort(key=lambda box: (box.y + box.height // 2, box.x))
        inverse = cv2.invertAffineTransform(matrix) if matrix is not None else None
        detected: list[DetectedLine] = []
        for order, box in enumerate(boxes):
            crop = deskewed_image.crop((box.x, box.y, box.right, box.bottom))
            polygon = self._source_polygon(box, inverse, width, height)
            source_box = self._polygon_bbox(polygon, width, height)
            detected.append(DetectedLine(source_box, order, crop, polygon))
        return detected

    @classmethod
    def _estimate_deskew_angle(cls, binary: np.ndarray) -> float:
        """Return the small rotation that makes the page's baselines horizontal."""

        height, width = binary.shape
        scale = min(1.0, 1200.0 / max(height, width))
        sample = (
            cv2.resize(binary, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            if scale < 1.0
            else binary
        )
        if np.count_nonzero(sample) < 100:
            return 0.0

        coarse = np.arange(-7.0, 7.01, 0.5)
        scores = [cls._projection_score(sample, float(angle)) for angle in coarse]
        best = float(coarse[int(np.argmax(scores))])
        fine = np.arange(best - 0.5, best + 0.501, 0.1)
        fine_scores = [cls._projection_score(sample, float(angle)) for angle in fine]
        best = float(fine[int(np.argmax(fine_scores))])
        zero_score = cls._projection_score(sample, 0.0)
        best_score = max(fine_scores)
        relative_gain = (best_score - zero_score) / max(zero_score, 1e-6)
        if abs(best) < 0.25 or relative_gain < 0.025:
            return 0.0
        return round(best, 2)

    @staticmethod
    def _projection_score(binary: np.ndarray, angle: float) -> float:
        height, width = binary.shape
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
        rotated = cv2.warpAffine(
            binary,
            matrix,
            (width, height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        margin_y = max(1, round(height * 0.03))
        margin_x = max(1, round(width * 0.03))
        profile = np.count_nonzero(
            rotated[margin_y : height - margin_y, margin_x : width - margin_x], axis=1
        ).astype(np.float64)
        total = float(profile.sum())
        return float(np.square(profile).sum() / max(total, 1.0))

    @staticmethod
    def _source_polygon(
        box: BoundingBox,
        inverse: np.ndarray | None,
        width: int,
        height: int,
    ) -> tuple[tuple[float, float], ...]:
        points = np.array(
            [
                [box.x, box.y, 1.0],
                [box.right, box.y, 1.0],
                [box.right, box.bottom, 1.0],
                [box.x, box.bottom, 1.0],
            ],
            dtype=np.float64,
        )
        if inverse is not None:
            points = points @ inverse.T
        return tuple(
            (
                float(np.clip(x, 0, max(0, width - 1))),
                float(np.clip(y, 0, max(0, height - 1))),
            )
            for x, y in points[:, :2]
        )

    @staticmethod
    def _polygon_bbox(
        polygon: tuple[tuple[float, float], ...], width: int, height: int
    ) -> BoundingBox:
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        left = max(0, int(np.floor(min(xs))))
        top = max(0, int(np.floor(min(ys))))
        right = min(width, int(np.ceil(max(xs))))
        bottom = min(height, int(np.ceil(max(ys))))
        return BoundingBox(left, top, max(1, right - left), max(1, bottom - top))

    @staticmethod
    def _clear_scan_edges(binary: np.ndarray) -> None:
        """Ignore common scanner borders and footer watermarks outside the page."""

        height, width = binary.shape
        x_margin = max(1, round(width * 0.01))
        top_margin = max(1, round(height * 0.01))
        bottom_margin = max(1, round(height * 0.035))
        binary[:, :x_margin] = 0
        binary[:, width - x_margin :] = 0
        binary[:top_margin, :] = 0
        binary[height - bottom_margin :, :] = 0

    @staticmethod
    def _smooth(profile: np.ndarray, height: int) -> np.ndarray:
        sigma = max(1.0, height / 700.0)
        kernel_size = max(3, int(round(sigma * 6)) | 1)
        return cv2.GaussianBlur(
            profile.reshape(-1, 1), (1, kernel_size), sigmaX=0, sigmaY=sigma
        ).ravel()

    @classmethod
    def _line_centres(
        cls, profile: np.ndarray, width: int, height: int
    ) -> list[int]:
        # A wide local-maximum window keeps ascenders and descenders from becoming
        # independent lines while still allowing the tight spacing in ledgers.
        window = max(9, int(round(height / 60.0)) | 1)
        local_maximum = cv2.dilate(
            profile.reshape(-1, 1), np.ones((window, 1), dtype=np.uint8)
        ).ravel()
        minimum_ink = max(8.0, width * 0.01)
        candidates = (profile >= local_maximum - 1e-6) & (profile >= minimum_ink)

        centres: list[int] = []
        for start, end in cls._bands(candidates):
            local = profile[start:end]
            centres.append(start + int(np.argmax(local)))

        # Antialiased or textured strokes can leave two nearby projection peaks
        # within one physical line after deskewing. Consolidate only peaks much
        # closer than normal line spacing, retaining the stronger centre.
        consolidated: list[int] = []
        minimum_separation = max(12, window * 2)
        for centre in centres:
            if consolidated and centre - consolidated[-1] < minimum_separation:
                if profile[centre] > profile[consolidated[-1]]:
                    consolidated[-1] = centre
            else:
                consolidated.append(centre)
        return consolidated

    @staticmethod
    def _valley_boundaries(
        profile: np.ndarray, centres: list[int], height: int
    ) -> list[tuple[int, int]]:
        if len(centres) == 1:
            radius = max(20, round(height * 0.08))
            return [(max(0, centres[0] - radius), min(height, centres[0] + radius))]

        separators: list[int] = []
        for upper, lower in zip(centres, centres[1:], strict=False):
            # Excluding the centres themselves prevents a weak line centre from
            # being selected as its own separator.
            start = upper + 1
            stop = max(start + 1, lower)
            separators.append(start + int(np.argmin(profile[start:stop])))

        first_extent = round((centres[1] - centres[0]) * 1.25)
        last_extent = round((centres[-1] - centres[-2]) * 1.25)
        first_bound = max(0, centres[0] - first_extent)
        last_bound = min(height, centres[-1] + last_extent)
        bounds = [first_bound, *separators, last_bound]
        return list(zip(bounds, bounds[1:], strict=False))

    @staticmethod
    def _remove_implausibly_tall_boxes(
        boxes: list[BoundingBox], page_height: int
    ) -> list[BoundingBox]:
        if len(boxes) < 3:
            return boxes
        typical_height = float(np.median([box.height for box in boxes]))
        # Real Kurrent lines can be over three times the median height because of
        # long descenders. Only reject page-scale regions beyond that allowance.
        limit = max(page_height * 0.10, typical_height * 3.5)
        return [box for box in boxes if box.height <= limit]

    def _boxes_in_band(
        self, binary: np.ndarray, top: int, bottom: int, centre: int
    ) -> list[BoundingBox]:
        height, width = binary.shape
        if bottom - top < self.minimum_height:
            return []

        band = binary[top:bottom, :]
        component_count, _, stats, _ = cv2.connectedComponentsWithStats(band, 8)
        components: list[tuple[int, int, int, int, int]] = []
        for index in range(1, component_count):
            x, relative_y, component_width, component_height, area = (
                int(value) for value in stats[index]
            )
            if area < 8 or component_width < 2 or component_height < 2:
                continue
            components.append(
                (x, top + relative_y, component_width, component_height, area)
            )
        if not components:
            return []

        # Keep spatially separated columns separate, but bridge ordinary word gaps.
        components.sort(key=lambda item: item[0])
        maximum_gap = max(24, round(width * 0.08))
        groups: list[list[tuple[int, int, int, int, int]]] = []
        for component in components:
            if not groups:
                groups.append([component])
                continue
            previous_right = max(item[0] + item[2] for item in groups[-1])
            if component[0] - previous_right <= maximum_gap:
                groups[-1].append(component)
            else:
                groups.append([component])

        boxes: list[BoundingBox] = []
        minimum_width = max(20, round(width * 0.03))
        for group in groups:
            left = min(item[0] for item in group)
            right = max(item[0] + item[2] for item in group)
            ink_top = min(item[1] for item in group)
            ink_bottom = max(item[1] + item[3] for item in group)
            area = sum(item[4] for item in group)
            if right - left < minimum_width or area < 30:
                continue

            padded_left = max(0, left - self.padding)
            padded_right = min(width, right + self.padding)
            padded_top = max(top, ink_top - self.padding)
            padded_bottom = min(bottom, ink_bottom + self.padding)
            if padded_bottom - padded_top < self.minimum_height:
                half = max(1, self.minimum_height // 2)
                padded_top = max(top, centre - half)
                padded_bottom = min(bottom, padded_top + self.minimum_height)
            boxes.append(
                BoundingBox(
                    padded_left,
                    padded_top,
                    padded_right - padded_left,
                    padded_bottom - padded_top,
                )
            )
        return boxes

    @staticmethod
    def _bands(mask: np.ndarray) -> list[tuple[int, int]]:
        padded = np.pad(mask.astype(np.int8), (1, 1))
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        return list(zip(starts.tolist(), ends.tolist(), strict=True))

