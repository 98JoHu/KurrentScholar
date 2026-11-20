from PIL import Image, ImageDraw

from kurrentscholar.segmentation import ProjectionSegmenter


def test_projection_segmenter_finds_ordered_lines():
    image = Image.new("RGB", (600, 300), "white")
    draw = ImageDraw.Draw(image)
    for y in (60, 160):
        draw.rectangle((70, y, 520, y + 18), fill="black")
    lines = ProjectionSegmenter(minimum_height=5).detect_lines(image)
    assert len(lines) == 2
    assert lines[0].bbox.y < lines[1].bbox.y
    assert [line.reading_order for line in lines] == [0, 1]


def test_blank_page_returns_no_lines():
    assert ProjectionSegmenter().detect_lines(Image.new("RGB", (200, 200), "white")) == []

