import hashlib
import json

from kurrentscholar.constants import ModelSpec
from kurrentscholar.recognition.model_manager import ModelManager


def make_spec(sizes, checksum="unused"):
    return ModelSpec(
        key="test",
        display_name="Test model",
        model_id="example/test-model",
        revision="abc123",
        doi=None,
        license="MIT",
        file_sizes=sizes,
        safetensors_sha256=checksum,
        max_new_tokens=42,
    )


def test_model_status_requires_all_files_sizes_and_revision(tmp_path):
    sizes = {"config.json": 3, "model.safetensors": 5}
    spec = make_spec(sizes)
    manager = ModelManager(tmp_path, spec)
    assert not manager.status().installed
    for name, size in sizes.items():
        (tmp_path / name).write_bytes(b"x" * size)
    (tmp_path / "kurrentscholar-model.json").write_text(
        json.dumps({"model_id": spec.model_id, "revision": spec.revision}), encoding="utf-8"
    )
    assert not manager.status().installed
    (tmp_path / "kurrentscholar-model.json").write_text(
        json.dumps({
            "model_id": spec.model_id,
            "revision": spec.revision,
            "model_safetensors_sha256": spec.safetensors_sha256,
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
    checksum = hashlib.sha256(contents["model.safetensors"]).hexdigest()
    spec = make_spec(sizes, checksum)
    import kurrentscholar.recognition.model_manager as model_manager_module

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
    manager = ModelManager(tmp_path, spec)
    monkeypatch.setattr(manager, "check_disk_space", lambda: True)
    messages = []
    manager.install(messages.append)
    assert len(attempts) == 2
    assert manager.status().installed
    assert any("retrying" in message for message in messages)

