import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from kurrentscholar.recognition import TrOCRBackend


@pytest.mark.real_model
def test_real_model_loads_and_generates_for_line_fixture():
    model_path = os.environ.get("KURRENTSCHOLAR_MODEL_PATH")
    fixture = os.environ.get("KURRENTSCHOLAR_LICENSED_LINE_FIXTURE")
    if not model_path:
        pytest.skip("Set KURRENTSCHOLAR_MODEL_PATH for real-model validation")
    if fixture:
        image = Image.open(fixture)
    else:
        # Architecture/score smoke input only; this is not an archival accuracy fixture.
        image = Image.new("RGB", (900, 90), "white")
        ImageDraw.Draw(image).text((20, 25), "KurrentScholar Modelltest 1874", fill="black")
    result = TrOCRBackend(Path(model_path)).recognize_line(image)
    assert isinstance(result.text, str)
    assert result.token_probabilities
    assert all(0 <= score <= 1 for score in result.token_probabilities)

