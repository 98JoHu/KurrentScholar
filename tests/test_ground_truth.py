import json
import zipfile

import pytest
from PIL import Image

from kurrentscholar.domain import BoundingBox, ReviewStatus
from kurrentscholar.ground_truth import GroundTruthError, export_training_bundle
from kurrentscholar.projects import ProjectDatabase


def ground_truth_project(tmp_path):
    source = tmp_path / "page.png"
    Image.new("RGB", (300, 180), "white").save(source)
    project = ProjectDatabase(tmp_path / "ground-truth.ksproj", create=True)
    project.set_document(source, 1)
    project.set_info({"model_id": "example/model", "model_revision": "pinned"})
    project.upsert_page(1, 300, 180, 300)
    for index in range(5):
        line_id = project.add_line(
            1, index, BoundingBox(10, 10 + index * 30, 250, 22),
            f"machine {index}", 0.8, [], [],
        )
        project.correct_line(line_id, f"verified {index}")
        project.set_review_status(line_id, ReviewStatus.VERIFIED)
    return project


def test_training_bundle_contains_verified_crops_labels_and_provenance(tmp_path):
    project = ground_truth_project(tmp_path)
    bundle = tmp_path / "training.zip"
    report = export_training_bundle(project, bundle, [1], [1])
    assert report["line_count"] == 5
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "lines/page-0001_line-0001.png" in names
        assert archive.read("lines/page-0001_line-0001.gt.txt").decode() == "verified 0"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["base_model"] == {"model_id": "example/model", "revision": "pinned"}
        assert manifest["target_pages"] == [1]
    project.close()


def test_training_bundle_rejects_partly_verified_reference_page(tmp_path):
    project = ground_truth_project(tmp_path)
    first = project.lines()[0]
    project.set_review_status(first.id, ReviewStatus.UNREVIEWED)
    with pytest.raises(GroundTruthError, match="Every detected line"):
        export_training_bundle(project, tmp_path / "bad.zip", [1], [1])
    project.close()
