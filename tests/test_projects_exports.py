import csv
import json
import sqlite3

from kurrentscholar.domain import BoundingBox, ReviewStatus
from kurrentscholar.exports import (
    ExportOptions,
    export_csv,
    export_docx,
    export_json,
    export_text,
    export_xlsx,
)
from kurrentscholar.projects import ProjectDatabase


def make_project(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    path = tmp_path / "research.ksproj"
    project = ProjectDatabase(path, create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)
    line_id = project.add_line(1, 0, BoundingBox(10, 20, 300, 40), "=machine", 0.7, [0.7], [42])
    return path, project, line_id


def test_project_preserves_machine_output_and_history(tmp_path):
    path, project, line_id = make_project(tmp_path)
    project.correct_line(line_id, "Korrektur äöü")
    project.set_review_status(line_id, ReviewStatus.VERIFIED)
    project.close()
    with ProjectDatabase(path) as reopened:
        line = reopened.lines()[0]
        assert line.machine_text == "=machine"
        assert line.display_text == "Korrektur äöü"
        assert line.review_status == "verified"


def test_v1_project_migrates_annotations_and_deskew_columns_transactionally(tmp_path):
    path = tmp_path / "legacy.ksproj"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA user_version=1;
        CREATE TABLE project_info (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO project_info VALUES ('schema_version', '1');
        CREATE TABLE pages (
          page_number INTEGER PRIMARY KEY, width INTEGER NOT NULL, height INTEGER NOT NULL,
          dpi INTEGER NOT NULL, rotation INTEGER NOT NULL DEFAULT 0,
          segmentation_status TEXT NOT NULL DEFAULT 'pending', segmentation_error TEXT,
          processed_at TEXT
        );
        CREATE TABLE lines (
          id INTEGER PRIMARY KEY, page_number INTEGER NOT NULL, reading_order INTEGER NOT NULL,
          x INTEGER NOT NULL, y INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
          machine_text TEXT NOT NULL DEFAULT '', corrected_text TEXT, confidence REAL,
          token_probabilities_json TEXT NOT NULL DEFAULT '[]', token_ids_json TEXT NOT NULL DEFAULT '[]',
          review_status TEXT NOT NULL DEFAULT 'unreviewed', notes TEXT NOT NULL DEFAULT '',
          truncated INTEGER NOT NULL DEFAULT 0, recognition_error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        INSERT INTO pages VALUES (1, 1000, 1500, 300, 0, 'segmented', NULL, 'now');
        INSERT INTO lines VALUES (
          1, 1, 0, 10, 20, 300, 40, 'legacy text', NULL, .8,
          '[]', '[]', 'unreviewed', '', 0, NULL, 'now', 'now'
        );
        """
    )
    connection.commit()
    connection.close()

    with ProjectDatabase(path) as project:
        assert project.connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert project.page(1)["deskew_angle"] == 0
        assert project.line(1).annotations == []
        assert project.line(1).polygon == []
    backup = tmp_path / "legacy.schema-v1-backup.ksproj"
    assert backup.is_file()
    connection = sqlite3.connect(backup)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    connection.close()


def test_identical_edit_is_not_added_to_history(tmp_path):
    _, project, line_id = make_project(tmp_path)
    assert not project.correct_line(line_id, "=machine")
    assert project.connection.execute("SELECT COUNT(*) FROM correction_history").fetchone()[0] == 0
    assert project.correct_line(line_id, "corrected")
    assert not project.correct_line(line_id, "corrected")
    assert project.connection.execute("SELECT COUNT(*) FROM correction_history").fetchone()[0] == 1
    project.close()


def test_reprocessing_does_not_replace_machine_or_human_text(tmp_path):
    _, project, line_id = make_project(tmp_path)
    project.correct_line(line_id, "human reading")
    project.add_line(1, 0, BoundingBox(20, 30, 400, 50), "new machine", 0.99, [0.99], [7])
    line = project.line(line_id)
    assert line.machine_text == "=machine"
    assert line.display_text == "human reading"
    assert line.bbox == BoundingBox(10, 20, 300, 40)
    project.close()


def test_project_creation_requires_explicit_overwrite(tmp_path):
    path, project, _ = make_project(tmp_path)
    project.close()
    import pytest

    with pytest.raises(FileExistsError):
        ProjectDatabase(path, create=True)
    replacement = ProjectDatabase(path, create=True, overwrite=True)
    assert replacement.document() is None
    assert replacement.lines() == []
    replacement.close()


def test_project_backup_and_transcription_reset_preserve_source(tmp_path):
    path, project, line_id = make_project(tmp_path)
    project.correct_line(line_id, "human reading")
    project.set_review_status(line_id, ReviewStatus.VERIFIED)
    summary = project.transcription_summary()
    assert summary == {"line_count": 1, "corrected_count": 1, "reviewed_count": 1}

    backup_path = tmp_path / "research.before-resegment.ksproj"
    project.backup_to(backup_path)
    project.reset_transcription()

    assert project.document() is not None
    assert project.lines() == []
    with ProjectDatabase(backup_path) as backup:
        assert backup.line(line_id).display_text == "human reading"
    project.close()


def test_exports_are_utf8_structured_and_csv_safe(tmp_path):
    _, project, line_id = make_project(tmp_path)
    project.correct_line(
        line_id,
        "H2O Straße",
        [
            {"start": 1, "end": 2, "kind": "subscript"},
            {"start": 4, "end": 10, "kind": "tag", "label": "Place", "color": "#C9DDF7"},
        ],
    )
    project.set_info({"model_id": "example/model", "model_revision": "pinned-revision"})
    text = tmp_path / "out.txt"
    data = tmp_path / "out.json"
    table = tmp_path / "out.csv"
    word = tmp_path / "out.docx"
    excel = tmp_path / "out.xlsx"
    export_text(project, text, ExportOptions(uncertainty_markers=True))
    export_json(project, data)
    export_csv(project, table)
    export_docx(project, word, ExportOptions(uncertainty_markers=True))
    export_xlsx(project, excel)
    assert "high_uncertainty" in text.read_text("utf-8")
    payload = json.loads(data.read_text("utf-8"))
    assert payload["lines"][0]["machine_text"] == "=machine"
    assert payload["provenance"]["model_id"] == "example/model"
    assert payload["provenance"]["model_revision"] == "pinned-revision"
    assert payload["lines"][0]["annotations"][0]["kind"] == "subscript"
    with table.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][3] == "'=machine"
    assert rows[1][12] == "Place"
    assert word.stat().st_size > 0
    from docx import Document

    word_document = Document(word)
    assert any(run.font.subscript for paragraph in word_document.paragraphs for run in paragraph.runs)
    assert any("Tags: Place" in paragraph.text for paragraph in word_document.paragraphs)
    from openpyxl import load_workbook

    workbook = load_workbook(excel, read_only=True, data_only=False)
    assert workbook.sheetnames == ["Transcription", "Summary", "Provenance"]
    assert workbook["Transcription"]["D2"].value == "'=machine"
    assert workbook["Transcription"]["F2"].value == "H2O Straße"
    assert workbook["Transcription"]["O2"].value == "Place"
    assert workbook["Provenance"]["B6"].value == project.document()["sha256"]
    workbook.close()
    import zipfile

    with zipfile.ZipFile(excel) as package:
        worksheet_xml = package.read("xl/worksheets/sheet1.xml").decode("utf-8")
        table_xml = package.read("xl/tables/table1.xml").decode("utf-8")
    assert "<autoFilter" not in worksheet_xml
    assert "<autoFilter" in table_xml
    assert 't="inlineStr"></c>' not in worksheet_xml
    project.close()


def test_relink_accepts_only_the_same_source_bytes(tmp_path):
    _, project, _ = make_project(tmp_path)
    moved = tmp_path / "moved-source.bin"
    moved.write_bytes(b"source")
    project.relink_document(moved)
    assert project.document()["source_path"] == str(moved.resolve())
    different = tmp_path / "different.bin"
    different.write_bytes(b"different")
    import pytest

    with pytest.raises(ValueError, match="checksum"):
        project.relink_document(different)
    project.close()

