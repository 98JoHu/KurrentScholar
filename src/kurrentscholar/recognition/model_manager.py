from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import snapshot_download

from kurrentscholar.constants import (
    MODEL_FILES,
    MODEL_ID,
    MODEL_REQUIRED_BYTES,
    MODEL_REVISION,
    default_data_dir,
)


@dataclass(frozen=True, slots=True)
class ModelStatus:
    installed: bool
    path: Path
    revision: str
    bytes_required: int
    missing_files: tuple[str, ...] = ()


class ModelManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_data_dir() / "models" / MODEL_REVISION

    def status(self) -> ModelStatus:
        missing = tuple(name for name in MODEL_FILES if not (self.root / name).is_file())
        manifest_ok = False
        try:
            manifest = json.loads((self.root / "kurrentscholar-model.json").read_text("utf-8"))
            manifest_ok = manifest.get("revision") == MODEL_REVISION
        except (OSError, ValueError):
            pass
        return ModelStatus(not missing and manifest_ok, self.root, MODEL_REVISION, MODEL_REQUIRED_BYTES, missing)

    def check_disk_space(self) -> bool:
        self.root.parent.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(self.root.parent).free >= MODEL_REQUIRED_BYTES + 512 * 1024 * 1024

    def install(self, progress: Callable[[str], None] | None = None) -> Path:
        if not self.check_disk_space():
            raise OSError("At least 1.8 GB of free space is required for the model and download cache")
        self.root.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("Downloading the pinned model files")
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            local_dir=self.root,
            allow_patterns=list(MODEL_FILES),
        )
        missing = [name for name in MODEL_FILES if not (self.root / name).is_file()]
        if missing:
            raise OSError(f"Model download is incomplete: {', '.join(missing)}")
        (self.root / "kurrentscholar-model.json").write_text(
            json.dumps({"model_id": MODEL_ID, "revision": MODEL_REVISION, "files": MODEL_FILES}, indent=2),
            encoding="utf-8",
        )
        return self.root

    def remove(self) -> None:
        marker = self.root / "kurrentscholar-model.json"
        try:
            manifest = json.loads(marker.read_text("utf-8"))
        except (OSError, ValueError) as error:
            raise OSError("Refusing to remove a directory without a KurrentScholar model manifest") from error
        if manifest.get("revision") != MODEL_REVISION or self.root.parent == self.root:
            raise OSError("Refusing to remove an unrecognized model directory")
        shutil.rmtree(self.root)

