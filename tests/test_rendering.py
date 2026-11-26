import pypdfium2 as pdfium
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

