from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kurrentscholar import __version__
from kurrentscholar.constants import MODEL_DOI, MODEL_ID, MODEL_REVISION, PROJECT_SCHEMA_VERSION
from kurrentscholar.domain import ConfidenceThresholds
from kurrentscholar.projects import ProjectDatabase


@dataclass(frozen=True, slots=True)
class ExportOptions:
    corrected: bool = True
    page_markers: bool = True
    line_numbers: bool = False
    uncertainty_markers: bool = False


def _text(line, corrected: bool) -> str:
    return line.display_text if corrected else line.machine_text


def _safe_csv(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def export_text(project: ProjectDatabase, destination: str | Path, options: ExportOptions) -> None:
    output: list[str] = []
    current_page = None
    thresholds = ConfidenceThresholds()
    for line in project.lines():
        if options.page_markers and line.page_number != current_page:
            if output:
                output.append("")
            output.append(f"[Page {line.page_number}]")
            current_page = line.page_number
        prefix = f"{line.reading_order + 1}: " if options.line_numbers else ""
        marker = f" [{thresholds.classify(line.confidence).value}]" if options.uncertainty_markers else ""
        output.append(prefix + _text(line, options.corrected) + marker)
    Path(destination).write_text("\n".join(output) + "\n", encoding="utf-8")


def export_csv(project: ProjectDatabase, destination: str | Path) -> None:
    document = project.document() or {}
    with Path(destination).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["document", "page", "line", "machine_text", "corrected_text", "confidence", "review_status",
             "x", "y", "width", "height", "notes"]
        )
        for line in project.lines():
            writer.writerow([_safe_csv(value) for value in (
                document.get("filename", ""), line.page_number, line.reading_order + 1, line.machine_text,
                line.corrected_text if line.corrected_text is not None else "",
                line.confidence, line.review_status, line.bbox.x, line.bbox.y,
                line.bbox.width, line.bbox.height, line.notes,
            )])


def export_json(project: ProjectDatabase, destination: str | Path) -> None:
    payload = {
        "schema": "urn:kurrentscholar:export:1",
        "schema_version": PROJECT_SCHEMA_VERSION,
        "provenance": {
            "software": "KurrentScholar",
            "software_version": __version__,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "model_doi": MODEL_DOI,
            **project.info(),
        },
        "document": {
            key: value
            for key, value in (project.document() or {}).items()
            if key != "source_path"
        },
        "metadata": project.metadata(),
        "lines": [
            {
                **asdict(line),
                "bbox": asdict(line.bbox),
                "effective_text": line.display_text,
                "verified": line.review_status == "verified",
            }
            for line in project.lines()
        ],
    }
    Path(destination).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_docx(project: ProjectDatabase, destination: str | Path, options: ExportOptions) -> None:
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    document = Document()
    document.add_heading(project.metadata().get("document_title", "Transcription"), 0)
    for key, value in project.metadata().items():
        if value:
            document.add_paragraph(f"{key.replace('_', ' ').title()}: {value}")
    current_page = None
    thresholds = ConfidenceThresholds()
    colors = {"moderate": WD_COLOR_INDEX.YELLOW, "high_uncertainty": WD_COLOR_INDEX.DARK_YELLOW,
              "very_high_uncertainty": WD_COLOR_INDEX.RED}
    for line in project.lines():
        if line.page_number != current_page:
            document.add_heading(f"Page {line.page_number}", level=1)
            current_page = line.page_number
        paragraph = document.add_paragraph()
        if options.line_numbers:
            paragraph.add_run(f"{line.reading_order + 1}: ")
        run = paragraph.add_run(_text(line, options.corrected))
        label = thresholds.classify(line.confidence).value
        if options.uncertainty_markers and label in colors:
            run.font.highlight_color = colors[label]
            paragraph.add_run(f" [{label.replace('_', ' ')}]")
    document.add_paragraph(
        f"Created with KurrentScholar {__version__}; recognition model {MODEL_ID} "
        f"({MODEL_REVISION}, doi:{MODEL_DOI}). Machine output may contain errors."
    )
    document.save(str(destination))

