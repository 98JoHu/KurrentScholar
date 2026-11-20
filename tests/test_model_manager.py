import json

from kurrentscholar.constants import MODEL_FILES, MODEL_REVISION
from kurrentscholar.recognition.model_manager import ModelManager


def test_model_status_requires_all_files_and_revision(tmp_path):
    manager = ModelManager(tmp_path)
    assert not manager.status().installed
    for name in MODEL_FILES:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "kurrentscholar-model.json").write_text(
        json.dumps({"revision": MODEL_REVISION}), encoding="utf-8"
    )
    assert manager.status().installed

