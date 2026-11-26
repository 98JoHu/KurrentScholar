from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_NAME = "KurrentScholar"
PROJECT_SCHEMA_VERSION = 3


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
    summary: str = ""

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
    summary="Best established choice for predominantly 19th-century German Kurrent.",
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
    summary="Broader 16th–19th-century comparison model; newer and still experimental.",
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

EARLY_KURRENT_MODEL = ModelSpec(
    key="kurrent-xvi-xviii-2023",
    display_name="Kurrent (16th–18th century; Swiss-biased)",
    model_id="dh-unibe/trocr-kurrent-XVI-XVII",
    revision="c599751f3f93fc80542aa0f4082ecaff0dd952bf",
    doi="10.57967/hf/0441",
    license="MIT",
    max_new_tokens=127,
    summary=(
        "For early-modern German Kurrent. Trained on a large but Swiss-biased corpus; "
        "the authors describe it as a starting point for further fine-tuning."
    ),
    file_sizes={
        "LICENSE": 1_102,
        "README.md": 2_250,
        "config.json": 4_874,
        "generation_config.json": 275,
        "merges.txt": 456_318,
        "model.safetensors": 1_335_747_112,
        "preprocessor_config.json": 325,
        "special_tokens_map.json": 772,
        "tokenizer_config.json": 1_118,
        "vocab.json": 898_822,
    },
    safetensors_sha256="dfb88d0a11fecc1fb92152a9d435e16c787bb6190c4995f277e4dfeb2976d065",
)

MODEL_CATALOG = (LEGACY_MODEL, EARLY_KURRENT_MODEL, BROAD_KURRENT_MODEL)
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


def default_data_dir() -> Path:
    from platformdirs import user_data_dir

    return Path(user_data_dir(APP_NAME, appauthor=False))


def default_log_dir() -> Path:
    from platformdirs import user_log_dir

    return Path(user_log_dir(APP_NAME, appauthor=False))

