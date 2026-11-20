from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True, slots=True)
class PreprocessSettings:
    grayscale: bool = True
    contrast: bool = True
    denoise: bool = False


def preprocess(image: Image.Image, settings: PreprocessSettings) -> Image.Image:
    array = np.asarray(image.convert("RGB"))
    if settings.grayscale:
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
        if settings.denoise:
            gray = cv2.medianBlur(gray, 3)
        if settings.contrast:
            gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        return Image.fromarray(gray).convert("RGB")
    return image.copy()

