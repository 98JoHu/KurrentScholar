from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from kurrentscholar import __version__
from kurrentscholar.document_processing import DocumentRenderer
from kurrentscholar.projects import ProjectDatabase
from kurrentscholar.segmentation.projection import deskew_image, recognition_crop


class GroundTruthError(ValueError):
    """The selected pages are not yet suitable as training ground truth."""


def export_training_bundle(
    project: ProjectDatabase,
    destination: str | Path,
    reference_pages: list[int],
    target_pages: list[int],
) -> dict[str, object]:
    """Export verified line images and labels for an external TrOCR fine-tune.

    Page numbers are one-based. The bundle intentionally does not train inside the
    desktop process: reliable fine-tuning needs a CUDA environment, validation split,
    checkpoints, and provenance controls that are outside the CPU-first application.
    """

    if not reference_pages:
        raise GroundTruthError("Select at least one reference page.")
    if not target_pages:
        raise GroundTruthError("Select at least one target page.")
    document = project.document()
    if not document:
        raise GroundTruthError("The project has no source document.")
    source = Path(document["source_path"])
    if not source.is_file():
        raise GroundTruthError("The original source document is missing.")

    selected_lines = []
    incomplete_pages: list[int] = []
    empty_pages: list[int] = []
    for page_number in reference_pages:
        lines = project.lines(page_number)
        if not lines:
            empty_pages.append(page_number)
            continue
        if any(line.review_status != "verified" for line in lines):
            incomplete_pages.append(page_number)
            continue
        selected_lines.extend(lines)
    if empty_pages:
        joined = ", ".join(map(str, empty_pages))
        raise GroundTruthError(f"Reference page(s) {joined} have no detected lines.")
    if incomplete_pages:
        joined = ", ".join(map(str, incomplete_pages))
        raise GroundTruthError(
            f"Every detected line must be checked and marked verified first. "
            f"Incomplete reference page(s): {joined}."
        )
    if len(selected_lines) < 5:
        raise GroundTruthError(
            "Fewer than five verified lines were selected. Add more ground truth before exporting."
        )

    info = project.info()
    manifest: dict[str, object] = {
        "schema": "urn:kurrentscholar:trocr-ground-truth:1",
        "created_with": f"KurrentScholar {__version__}",
        "source": {
            "filename": document["filename"],
            "sha256": document["sha256"],
        },
        "base_model": {
            "model_id": info.get("model_id"),
            "revision": info.get("model_revision"),
        },
        "reference_pages": reference_pages,
        "target_pages": target_pages,
        "line_count": len(selected_lines),
        "lines": [],
    }
    renderer = DocumentRenderer()
    rendered_pages = {}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for line in selected_lines:
            page = project.page(line.page_number)
            if not page:
                raise GroundTruthError(f"Page {line.page_number} has no stored geometry.")
            deskew_angle = float(page.get("deskew_angle") or 0.0)
            key = (line.page_number, int(page["dpi"]), deskew_angle)
            page_image = rendered_pages.get(key)
            if page_image is None:
                rendered = renderer.render(source, line.page_number - 1, dpi=key[1])
                # Recognition saw lines cut from the deskewed page; training crops must match.
                page_image = deskew_image(rendered.image, deskew_angle)
                rendered_pages[key] = page_image
            box = line.bbox
            if deskew_angle and line.polygon:
                crop = recognition_crop(page_image, line.polygon, deskew_angle)
            else:
                crop = page_image.crop((box.x, box.y, box.right, box.bottom))
            stem = f"page-{line.page_number:04d}_line-{line.reading_order + 1:04d}"
            image_name = f"lines/{stem}.png"
            label_name = f"lines/{stem}.gt.txt"
            image_buffer = io.BytesIO()
            crop.save(image_buffer, format="PNG", optimize=True)
            archive.writestr(image_name, image_buffer.getvalue())
            archive.writestr(label_name, line.display_text.encode("utf-8"))
            manifest["lines"].append({
                "image": image_name,
                "label": label_name,
                "page": line.page_number,
                "line": line.reading_order + 1,
                "bbox": [box.x, box.y, box.width, box.height],
                "deskew_angle": deskew_angle,
                "text": line.display_text,
            })
        archive.writestr(
            "README.txt",
            (
                "KurrentScholar TrOCR ground-truth bundle\n\n"
                "Each PNG has a UTF-8 .gt.txt label with the same stem. manifest.json records "
                "the pinned base model, source checksum, reference pages, and intended target "
                "pages. Fine-tuning is intentionally external: use a CUDA training environment, "
                "hold out validation pages, and keep the base model and resulting checkpoint "
                "provenance. A single page commonly overfits; evaluate before using an adapted "
                "model on the target range.\n"
            ),
        )
        archive.writestr(
            "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    return manifest
