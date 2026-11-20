from __future__ import annotations

from pathlib import Path

APP_NAME = "KurrentScholar"
PROJECT_SCHEMA_VERSION = 1
MODEL_ID = "dh-unibe/trocr-kurrent"
MODEL_REVISION = "2882072ac68f7aa09353a71092ebd5510f4b82cd"
MODEL_DOI = "10.57967/hf/0442"
MODEL_LICENSE = "MIT"
MODEL_REQUIRED_BYTES = 1_340_570_347
MODEL_FILE_SIZES = {
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
}
MODEL_FILES = tuple(MODEL_FILE_SIZES)
MODEL_SAFETENSORS_SHA256 = "7752d0843f90ff1933663eabd3182ac0b8f18f5e09edd23de0a3d96e76f42ddf"


def default_data_dir() -> Path:
    from platformdirs import user_data_dir

    return Path(user_data_dir(APP_NAME, appauthor=False))


def default_log_dir() -> Path:
    from platformdirs import user_log_dir

    return Path(user_log_dir(APP_NAME, appauthor=False))

