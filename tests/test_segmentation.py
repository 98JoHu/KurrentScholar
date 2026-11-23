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


def test_descender_connecting_lines_does_not_create_multiline_block():
    image = Image.new("RGB", (800, 500), "white")
    draw = ImageDraw.Draw(image)
    for y in (90, 200, 310):
        draw.rectangle((90, y, 700, y + 20), fill="black")
    # Simulate a long Kurrent descender crossing the whitespace between lines.
    draw.rectangle((360, 108, 366, 208), fill="black")

    lines = ProjectionSegmenter(minimum_height=5).detect_lines(image)

    assert len(lines) == 3
    assert max(line.bbox.height for line in lines) < 150


def test_scan_edges_and_footer_watermark_are_ignored():
    image = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 6, 599), fill="black")
    draw.rectangle((100, 160, 680, 180), fill="black")
    draw.rectangle((120, 280, 650, 300), fill="black")
    draw.rectangle((400, 582, 760, 598), fill="black")

    lines = ProjectionSegmenter(minimum_height=5).detect_lines(image)

    assert len(lines) == 2
    assert all(line.bbox.y < 400 for line in lines)


def test_paper_shadow_does_not_become_an_ink_block():
    array = Image.new("L", (800, 600), 235)
    draw = ImageDraw.Draw(array)
    draw.rectangle((80, 140, 700, 165), fill=35)
    draw.rectangle((100, 260, 680, 285), fill=45)
    # A pale scanner shadow is below Otsu's likely split, but is not ink.
    draw.rectangle((0, 360, 799, 540), fill=205)

    lines = ProjectionSegmenter(minimum_height=5).detect_lines(array.convert("RGB"))

    assert len(lines) == 2
    assert all(line.bbox.y < 350 for line in lines)


def test_slanted_page_is_deskewed_for_line_crops_and_keeps_rotated_overlays():
    image = Image.new("RGB", (800, 500), "white")
    draw = ImageDraw.Draw(image)
    for y in (110, 220, 330):
        draw.rectangle((90, y, 710, y + 18), fill="black")
    slanted = image.rotate(4.0, resample=Image.Resampling.BICUBIC, fillcolor="white")

    segmenter = ProjectionSegmenter(minimum_height=5)
    lines = segmenter.detect_lines(slanted)

    assert len(lines) == 3
    assert abs(segmenter.last_deskew_angle) >= 3.0
    assert all(line.crop is not None for line in lines)
    assert all(len(line.polygon) == 4 for line in lines)
    assert any(abs(line.polygon[0][1] - line.polygon[1][1]) > 10 for line in lines)

