from __future__ import annotations

from pathlib import Path

APP_NAME = "KurrentScholar"
PROJECT_SCHEMA_VERSION = 1
MODEL_ID = "dh-unibe/trocr-kurrent"
MODEL_REVISION = "2882072ac68f7aa09353a71092ebd5510f4b82cd"
MODEL_DOI = "10.57967/hf/0442"
MODEL_LICENSE = "MIT"
MODEL_REQUIRED_BYTES = 1_340_570_347
MODEL_FILES = (
    "LICENSE",
    "README.md",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)


def default_data_dir() -> Path:
    from platformdirs import user_data_dir

    return Path(user_data_dir(APP_NAME, appauthor=False))

