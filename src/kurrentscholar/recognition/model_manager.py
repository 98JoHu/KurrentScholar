from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from kurrentscholar.constants import (
    APP_NAME,
    DEFAULT_MODEL,
    ModelSpec,
    default_data_dir,
)
from kurrentscholar.diagnostics import exception_details

LOGGER = logging.getLogger(f"{APP_NAME}.model_install")


class ModelInstallError(RuntimeError):
    """An actionable model installation failure."""


@dataclass(frozen=True, slots=True)
class ModelStatus:
    installed: bool
    path: Path
    revision: str
    bytes_required: int
    missing_files: tuple[str, ...] = ()
    invalid_files: tuple[str, ...] = ()


class ModelManager:
    def __init__(self, root: Path | None = None, spec: ModelSpec = DEFAULT_MODEL) -> None:
        self.spec = spec
        self.root = root or default_data_dir() / "models" / spec.revision

    def status(self) -> ModelStatus:
        missing = []
        invalid = []
        for name, expected in self.spec.file_sizes.items():
            path = self.root / name
            try:
                if not path.is_file():
                    missing.append(name)
                elif path.stat().st_size != expected:
                    invalid.append(name)
            except OSError:
                invalid.append(name)
        manifest_ok = False
        try:
            manifest = json.loads((self.root / "kurrentscholar-model.json").read_text("utf-8"))
            manifest_ok = (
                manifest.get("model_id") == self.spec.model_id
                and manifest.get("revision") == self.spec.revision
                and manifest.get("model_safetensors_sha256") == self.spec.safetensors_sha256
            )
        except (OSError, ValueError):
            pass
        return ModelStatus(
            not missing and not invalid and manifest_ok,
            self.root,
            self.spec.revision,
            self.spec.required_bytes,
            tuple(missing),
            tuple(invalid),
        )

    def check_disk_space(self) -> bool:
        self.root.parent.mkdir(parents=True, exist_ok=True)
        remaining = max(0, self.spec.required_bytes - self.downloaded_bytes())
        return shutil.disk_usage(self.root.parent).free >= remaining + 512 * 1024 * 1024

    def downloaded_bytes(self) -> int:
        completed = 0
        for name, expected in self.spec.file_sizes.items():
            path = self.root / name
            try:
                if path.is_file():
                    completed += min(path.stat().st_size, expected)
            except OSError:
                continue
        partial = 0
        cache = self.root / ".cache"
        if cache.is_dir():
            try:
                partial = sum(
                    item.stat().st_size
                    for item in cache.rglob("*.incomplete")
                    if item.is_file()
                )
            except OSError:
                pass
        return min(self.spec.required_bytes, completed + partial)

    def install(self, progress: Callable[[str], None] | None = None) -> Path:
        def report(message: str) -> None:
            LOGGER.info("Model installation stage: %s", message)
            if progress:
                progress(message)

        if not self.check_disk_space():
            required_gib = (self.spec.required_bytes + 512 * 1024 * 1024) / (1024 ** 3)
            raise ModelInstallError(
                f"At least {required_gib:.2f} GiB of free disk space is required for this model "
                "and its resumable download cache."
            )
        self.root.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("DO_NOT_TRACK", "1")
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
        from huggingface_hub import snapshot_download
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()

        LOGGER.info(
            "Installing %s at revision %s into %s",
            self.spec.model_id,
            self.spec.revision,
            self.root,
        )
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                report(
                    f"Downloading the pinned model ‘{self.spec.display_name}’ "
                    f"(attempt {attempt}/3). Interrupted downloads resume automatically."
                )
                download_started = time.monotonic()
                snapshot_download(
                    repo_id=self.spec.model_id,
                    revision=self.spec.revision,
                    local_dir=self.root,
                    allow_patterns=list(self.spec.files),
                    max_workers=2,
                )
                LOGGER.info(
                    "Hugging Face snapshot download returned after %.1f seconds",
                    time.monotonic() - download_started,
                )
                last_error = None
                break
            except Exception as error:
                last_error = error
                LOGGER.error(
                    "Model download attempt %s failed\n%s", attempt, exception_details(error)
                )
                if attempt < 3:
                    report(f"Download attempt {attempt} failed; retrying shortly…")
                    time.sleep(2 ** (attempt - 1))
        if last_error is not None:
            raise ModelInstallError(self._friendly_download_error(last_error)) from last_error

        report("Checking the downloaded model files…")
        status = self.status()
        if status.missing_files or status.invalid_files:
            details = []
            if status.missing_files:
                details.append("missing: " + ", ".join(status.missing_files))
            if status.invalid_files:
                details.append("wrong size: " + ", ".join(status.invalid_files))
                for name in status.invalid_files:
                    # Remove only known managed files so the next attempt cannot
                    # mistake a truncated file for a completed download.
                    (self.root / name).unlink(missing_ok=True)
            raise ModelInstallError("The model download is incomplete (" + "; ".join(details) + ").")
        report(
            f"Verifying model integrity (about {self.spec.required_bytes / 1_000_000_000:.2f} GB). "
            "This can take a little while; KurrentScholar remains usable."
        )
        hash_started = time.monotonic()
        actual_hash = self._sha256(self.root / "model.safetensors")
        LOGGER.info("Model checksum completed after %.1f seconds", time.monotonic() - hash_started)
        if actual_hash != self.spec.safetensors_sha256:
            LOGGER.error("Safetensors checksum mismatch: %s", actual_hash)
            # Hugging Face Hub will fetch the file again on the next retry when
            # the corrupt destination is absent; its resumable cache is retained.
            (self.root / "model.safetensors").unlink(missing_ok=True)
            raise ModelInstallError(
                "The downloaded model failed its integrity check. Retry the installation; "
                "if it fails again, see the diagnostic log."
            )
        report("Finalizing the verified model installation…")
        (self.root / "kurrentscholar-model.json").write_text(
            json.dumps(
                {
                    "model_id": self.spec.model_id,
                    "revision": self.spec.revision,
                    "files": self.spec.file_sizes,
                    "model_safetensors_sha256": self.spec.safetensors_sha256,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        LOGGER.info("Model installation completed and verified")
        report("Model verified and ready for offline use.")
        return self.root

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _friendly_download_error(error: Exception) -> str:
        message = str(error).strip() or error.__class__.__name__
        lowered = message.lower()
        if "certificate" in lowered or "ssl" in lowered:
            return (
                "A secure connection to Hugging Face could not be established. Check the computer's "
                "date/time, HTTPS-inspecting antivirus or institutional proxy, then retry. "
                f"Technical cause: {message}"
            )
        if "permission" in lowered or "access is denied" in lowered:
            return (
                "KurrentScholar cannot write to its model folder. Check folder permissions and retry. "
                f"Technical cause: {message}"
            )
        if "timed out" in lowered or "connection" in lowered or "network" in lowered:
            return (
                "The model server could not be reached. Check the internet connection, VPN, firewall, "
                f"or institutional proxy and retry. Technical cause: {message}"
            )
        return f"The model download failed after three attempts. Technical cause: {message}"

    def remove(self) -> None:
        marker = self.root / "kurrentscholar-model.json"
        if not self.root.exists():
            return
        expected_root = default_data_dir() / "models" / self.spec.revision
        try:
            manifest = json.loads(marker.read_text("utf-8"))
        except (OSError, ValueError) as error:
            # Interrupted downloads have no final marker yet. Only the canonical
            # app-owned directory may be removed in that state; custom paths still
            # require a verified manifest.
            try:
                canonical_partial = self.root.resolve() == expected_root.resolve()
            except OSError:
                canonical_partial = False
            if not canonical_partial:
                raise OSError(
                    "Refusing to remove a directory without a KurrentScholar model manifest"
                ) from error
            manifest = None
        if manifest is not None and (
            manifest.get("model_id") != self.spec.model_id
            or manifest.get("revision") != self.spec.revision
        ):
            raise OSError("Refusing to remove an unrecognized model directory")
        if self.root.parent == self.root:
            raise OSError("Refusing to remove a filesystem root")
        shutil.rmtree(self.root)

