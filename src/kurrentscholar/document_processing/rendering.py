from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

MAX_IMAGE_PIXELS = 120_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


@dataclass(slots=True)
class RenderedPage:
    page_index: int
    image: Image.Image
    dpi: int
    rotation: int = 0


class DocumentRenderer:
    SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}

    def page_count(self, path: str | Path) -> int:
        source = Path(path)
        if source.suffix.lower() == ".pdf":
            import pypdfium2 as pdfium

            try:
                document = pdfium.PdfDocument(str(source))
                try:
                    return len(document)
                finally:
                    document.close()
            except Exception as error:
                raise ValueError("The PDF could not be opened. It may be damaged or encrypted.") from error
        if source.suffix.lower() in self.SUPPORTED_IMAGES:
            return 1
        raise ValueError("Choose a PDF, PNG, JPEG, or TIFF file")

    def render(self, path: str | Path, page_index: int, dpi: int = 300, rotation: int = 0) -> RenderedPage:
        if not 72 <= dpi <= 600:
            raise ValueError("Rendering resolution must be between 72 and 600 DPI")
        if rotation % 90:
            raise ValueError("Rotation must be a multiple of 90 degrees")
        source = Path(path)
        if source.suffix.lower() == ".pdf":
            image = self._render_pdf(source, page_index, dpi)
        elif source.suffix.lower() in self.SUPPORTED_IMAGES and page_index == 0:
            try:
                with Image.open(source) as opened:
                    opened.verify()
                with Image.open(source) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
            except Exception as error:
                raise ValueError("The image could not be opened or is damaged") from error
        else:
            raise ValueError("Invalid page number or unsupported document format")
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("The rendered page is too large; lower the DPI setting")
        normalized_rotation = rotation % 360
        if normalized_rotation:
            image = image.rotate(-normalized_rotation, expand=True, fillcolor="white")
        return RenderedPage(page_index, image, dpi, normalized_rotation)

    @staticmethod
    def _render_pdf(source: Path, page_index: int, dpi: int) -> Image.Image:
        import pypdfium2 as pdfium

        try:
            document = pdfium.PdfDocument(str(source))
            try:
                if not 0 <= page_index < len(document):
                    raise ValueError("Page number is outside the document")
                page = document[page_index]
                try:
                    bitmap = page.render(scale=dpi / 72.0, rev_byteorder=True)
                    try:
                        return bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                document.close()
        except ValueError:
            raise
        except Exception as error:
            raise ValueError("The PDF page could not be rendered") from error

