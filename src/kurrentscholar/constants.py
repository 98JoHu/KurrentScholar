from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_NAME = "KurrentScholar"
PROJECT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ModelSpec:
    key: str
    display_name: str
    model_id: str
    revision: str
    doi: str | None
    license: str
    file_sizes: dict[str, int]
    safetensors_sha256: str
    max_new_tokens: int
    recommended: bool = False

    @property
    def files(self) -> tuple[str, ...]:
        return tuple(self.file_sizes)

    @property
    def required_bytes(self) -> int:
        return sum(self.file_sizes.values())


LEGACY_MODEL = ModelSpec(
    key="kurrent-xix-2023",
    display_name="Kurrent (19th century, 2023; established default)",
    model_id="dh-unibe/trocr-kurrent",
    revision="2882072ac68f7aa09353a71092ebd5510f4b82cd",
    doi="10.57967/hf/0442",
    license="MIT",
    max_new_tokens=127,
    recommended=True,
    file_sizes={
        "LICENSE": 1_102,
        "README.md": 1_997,
        "config.json": 4_884,
        "generation_config.json": 275,
        "merges.txt": 456_318,
        "model.safetensors": 1_335_747_112,
        "preprocessor_config.json": 325,
        "special_tokens_map.json": 280,
        "tokenizer.json": 3_558_643,
        "tokenizer_config.json": 1_118,
        "vocab.json": 798_293,
    },
    safetensors_sha256="7752d0843f90ff1933663eabd3182ac0b8f18f5e09edd23de0a3d96e76f42ddf",
)

BROAD_KURRENT_MODEL = ModelSpec(
    key="kurrent-xvi-xix-2026",
    display_name="Kurrent (16th–19th century, 2026; experimental comparison)",
    model_id="dh-unibe/trocr-german-kurrent-xvi-xix-from-kurrent-v2",
    revision="bd1d96b67225b580846d7759f6ba74c66f56680e",
    doi=None,
    license="MIT",
    max_new_tokens=256,
    file_sizes={
        "LICENSE": 1_102,
        "README.md": 14_664,
        "config.json": 1_690,
        "generation_config.json": 339,
        "merges.txt": 456_318,
        "model.safetensors": 1_335_747_032,
        "preprocessor_config.json": 390,
        "special_tokens_map.json": 957,
        "tokenizer.json": 3_558_642,
        "tokenizer_config.json": 1_284,
        "vocab.json": 798_293,
    },
    safetensors_sha256="054474de1f621f61d1284ee4f274c58def0bb887b1a91694081960fb05dbaf3c",
)

MODEL_CATALOG = (LEGACY_MODEL, BROAD_KURRENT_MODEL)
DEFAULT_MODEL = LEGACY_MODEL


def find_model(model_id: str, revision: str) -> ModelSpec | None:
    return next(
        (
            spec
            for spec in MODEL_CATALOG
            if spec.model_id == model_id and spec.revision == revision
        ),
        None,
    )


# Backwards-compatible aliases for integrations that imported the original
# single-model constants. They describe the established default model.
MODEL_ID = DEFAULT_MODEL.model_id
MODEL_REVISION = DEFAULT_MODEL.revision
MODEL_DOI = DEFAULT_MODEL.doi
MODEL_LICENSE = DEFAULT_MODEL.license
MODEL_REQUIRED_BYTES = DEFAULT_MODEL.required_bytes
MODEL_FILE_SIZES = DEFAULT_MODEL.file_sizes
MODEL_FILES = DEFAULT_MODEL.files
MODEL_SAFETENSORS_SHA256 = DEFAULT_MODEL.safetensors_sha256


def default_data_dir() -> Path:
    from platformdirs import user_data_dir

    return Path(user_data_dir(APP_NAME, appauthor=False))


def default_log_dir() -> Path:
    from platformdirs import user_log_dir

    return Path(user_log_dir(APP_NAME, appauthor=False))

