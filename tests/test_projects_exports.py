import csv
import json

from kurrentscholar.domain import BoundingBox, ReviewStatus
from kurrentscholar.exports import ExportOptions, export_csv, export_docx, export_json, export_text
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


def test_exports_are_utf8_structured_and_csv_safe(tmp_path):
    _, project, _ = make_project(tmp_path)
    text = tmp_path / "out.txt"
    data = tmp_path / "out.json"
    table = tmp_path / "out.csv"
    word = tmp_path / "out.docx"
    export_text(project, text, ExportOptions(uncertainty_markers=True))
    export_json(project, data)
    export_csv(project, table)
    export_docx(project, word, ExportOptions(uncertainty_markers=True))
    assert "high_uncertainty" in text.read_text("utf-8")
    assert json.loads(data.read_text("utf-8"))["lines"][0]["machine_text"] == "=machine"
    with table.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][3] == "'=machine"
    assert word.stat().st_size > 0
    project.close()

