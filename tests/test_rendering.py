import pypdfium2 as pdfium
import pytest
from PIL import Image

from kurrentscholar.document_processing import DocumentRenderer


def test_image_render_keeps_native_size(tmp_path):
    source = tmp_path / "scan.png"
    Image.new("RGB", (40, 20), "white").save(source)
    renderer = DocumentRenderer()
    assert renderer.page_count(source) == 1
    page = renderer.render(source, 0, 300)
    assert page.image.size == (40, 20)


def test_pdf_page_count_and_render(tmp_path):
    source = tmp_path / "scan.pdf"
    document = pdfium.PdfDocument.new()
    document.new_page(200, 100)
    document.save(source)
    renderer = DocumentRenderer()
    assert renderer.page_count(source) == 1
    page = renderer.render(source, 0, 144)
    assert page.image.size == (400, 200)


def test_multi_page_tiff_exposes_every_page(tmp_path):
    source = tmp_path / "scan.tif"
    first = Image.new("RGB", (40, 20), "white")
    second = Image.new("RGB", (30, 50), "black")
    first.save(source, save_all=True, append_images=[second])
    renderer = DocumentRenderer()
    assert renderer.page_count(source) == 2
    assert renderer.render(source, 0, 300).image.size == (40, 20)
    page = renderer.render(source, 1, 300)
    assert page.image.size == (30, 50)
    assert page.image.getpixel((0, 0)) == (0, 0, 0)
    with pytest.raises(ValueError):
        renderer.render(source, 2, 300)


def test_single_page_image_rejects_other_pages(tmp_path):
    source = tmp_path / "scan.png"
    Image.new("RGB", (40, 20), "white").save(source)
    with pytest.raises(ValueError):
        DocumentRenderer().render(source, 1, 300)
