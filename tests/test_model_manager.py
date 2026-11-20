import hashlib
import json

import kurrentscholar.recognition.model_manager as model_manager_module
from kurrentscholar.constants import MODEL_REVISION
from kurrentscholar.recognition.model_manager import ModelManager


def test_model_status_requires_all_files_sizes_and_revision(tmp_path, monkeypatch):
    sizes = {"config.json": 3, "model.safetensors": 5}
    monkeypatch.setattr(model_manager_module, "MODEL_FILES", tuple(sizes))
    monkeypatch.setattr(model_manager_module, "MODEL_FILE_SIZES", sizes)
    manager = ModelManager(tmp_path)
    assert not manager.status().installed
    for name, size in sizes.items():
        (tmp_path / name).write_bytes(b"x" * size)
    (tmp_path / "kurrentscholar-model.json").write_text(
        json.dumps({"revision": MODEL_REVISION}), encoding="utf-8"
    )
    assert not manager.status().installed
    (tmp_path / "kurrentscholar-model.json").write_text(
        json.dumps({
            "revision": MODEL_REVISION,
            "model_safetensors_sha256": model_manager_module.MODEL_SAFETENSORS_SHA256,
        }),
        encoding="utf-8",
    )
    assert manager.status().installed
    (tmp_path / "config.json").write_bytes(b"wrong")
    status = manager.status()
    assert not status.installed
    assert status.invalid_files == ("config.json",)


def test_install_retries_then_verifies_and_writes_manifest(tmp_path, monkeypatch):
    contents = {"config.json": b"cfg", "model.safetensors": b"safe"}
    sizes = {name: len(value) for name, value in contents.items()}
    monkeypatch.setattr(model_manager_module, "MODEL_FILES", tuple(sizes))
    monkeypatch.setattr(model_manager_module, "MODEL_FILE_SIZES", sizes)
    monkeypatch.setattr(model_manager_module, "MODEL_REQUIRED_BYTES", sum(sizes.values()))
    monkeypatch.setattr(
        model_manager_module,
        "MODEL_SAFETENSORS_SHA256",
        hashlib.sha256(contents["model.safetensors"]).hexdigest(),
    )
    monkeypatch.setattr(model_manager_module.time, "sleep", lambda _seconds: None)
    attempts = []

    def snapshot_download(**_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("temporary network failure")
        for name, value in contents.items():
            (tmp_path / name).write_bytes(value)

    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "snapshot_download", snapshot_download)
    manager = ModelManager(tmp_path)
    monkeypatch.setattr(manager, "check_disk_space", lambda: True)
    messages = []
    manager.install(messages.append)
    assert len(attempts) == 2
    assert manager.status().installed
    assert any("retrying" in message for message in messages)

