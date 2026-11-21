from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kurrentscholar import __version__
from kurrentscholar.constants import DEFAULT_MODEL, PROJECT_SCHEMA_VERSION, find_model
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


def _safe_xlsx(value: object) -> object:
    """Keep Excel-safe text while representing empty spreadsheet cells as blanks."""

    safe = _safe_csv(value)
    return None if safe == "" else safe


def _model_provenance(project: ProjectDatabase) -> dict[str, str | None]:
    info = project.info()
    model_id = info.get("model_id", DEFAULT_MODEL.model_id)
    revision = info.get("model_revision", DEFAULT_MODEL.revision)
    spec = find_model(model_id, revision)
    return {
        "model_id": model_id,
        "model_revision": revision,
        "model_doi": spec.doi if spec else None,
    }


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
    model = _model_provenance(project)
    payload = {
        "schema": "urn:kurrentscholar:export:1",
        "schema_version": PROJECT_SCHEMA_VERSION,
        "provenance": {
            "software": "KurrentScholar",
            "software_version": __version__,
            **project.info(),
            **model,
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
    model = _model_provenance(project)
    doi = f", doi:{model['model_doi']}" if model["model_doi"] else ""
    document.add_paragraph(
        f"Created with KurrentScholar {__version__}; recognition model {model['model_id']} "
        f"({model['model_revision']}{doi}). Machine output may contain errors."
    )
    document.save(str(destination))


def export_xlsx(project: ProjectDatabase, destination: str | Path) -> None:
    """Create an analysis-friendly workbook without embedding private source paths."""

    from openpyxl import Workbook
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo

    workbook = Workbook()
    transcript = workbook.active
    transcript.title = "Transcription"
    headers = [
        "Document", "Page", "Line", "Machine text", "Corrected text", "Effective text",
        "Confidence", "Uncertainty", "Review status", "X", "Y", "Width", "Height", "Notes",
    ]
    transcript.append(headers)
    document = project.document() or {}
    thresholds = ConfidenceThresholds()
    lines = project.lines()
    for line in lines:
        transcript.append([
            _safe_xlsx(document.get("filename", "")),
            line.page_number,
            line.reading_order + 1,
            _safe_xlsx(line.machine_text),
            _safe_xlsx(line.corrected_text if line.corrected_text is not None else ""),
            _safe_xlsx(line.display_text),
            line.confidence,
            thresholds.classify(line.confidence).value,
            line.review_status,
            line.bbox.x,
            line.bbox.y,
            line.bbox.width,
            line.bbox.height,
            _safe_xlsx(line.notes),
        ])
    header_fill = PatternFill("solid", fgColor="9A6F6B")
    for cell in transcript[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center")
    transcript.freeze_panes = "A2"
    transcript.sheet_view.showGridLines = False
    widths = [24, 8, 8, 42, 42, 42, 12, 20, 16, 9, 9, 9, 9, 28]
    for index, width in enumerate(widths, start=1):
        transcript.column_dimensions[chr(64 + index)].width = width
    for row in transcript.iter_rows(min_row=2):
        for cell in row:
            if cell.value is not None:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    for cell in transcript["G"][1:]:
        cell.number_format = "0.0%"
    if lines:
        table = Table(displayName="KurrentScholarTranscription", ref=f"A1:N{transcript.max_row}")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        transcript.add_table(table)
        transcript.conditional_formatting.add(
            f"G2:G{transcript.max_row}",
            ColorScaleRule(
                start_type="num", start_value=0, start_color="F2B8B5",
                mid_type="num", mid_value=0.8, mid_color="FFF0C2",
                end_type="num", end_value=1, end_color="C7E7D4",
            ),
        )

    summary = workbook.create_sheet("Summary")
    summary.append(["Measure", "Value"])
    counts: dict[str, int] = {}
    for line in lines:
        label = thresholds.classify(line.confidence).value
        counts[label] = counts.get(label, 0) + 1
    summary_rows = [
        ("Document", document.get("filename", "")),
        ("Pages in source", document.get("page_count", 0)),
        ("Transcribed lines", len(lines)),
        ("Corrected lines", sum(line.corrected_text is not None for line in lines)),
        ("Verified lines", sum(line.review_status == "verified" for line in lines)),
        ("High confidence", counts.get("higher", 0)),
        ("Moderate uncertainty", counts.get("moderate", 0)),
        ("High uncertainty", counts.get("high_uncertainty", 0)),
        ("Very high uncertainty", counts.get("very_high_uncertainty", 0)),
        ("Unavailable confidence", counts.get("unavailable", 0)),
    ]
    for row in summary_rows:
        summary.append([_safe_xlsx(value) for value in row])
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 48

    provenance = workbook.create_sheet("Provenance")
    provenance.append(["Field", "Value"])
    model = _model_provenance(project)
    provenance_rows = {
        "Software": "KurrentScholar",
        "Software version": __version__,
        "Project schema": PROJECT_SCHEMA_VERSION,
        "Source filename": document.get("filename", ""),
        "Source SHA-256": document.get("sha256", ""),
        **project.info(),
        **model,
    }
    for key, value in provenance_rows.items():
        provenance.append([key.replace("_", " ").title(), _safe_xlsx(value or "")])
    provenance.column_dimensions["A"].width = 28
    provenance.column_dimensions["B"].width = 72

    for sheet in (summary, provenance):
        sheet.freeze_panes = "A2"
        sheet.sheet_view.showGridLines = False
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if cell.value is not None:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
    workbook.save(destination)

