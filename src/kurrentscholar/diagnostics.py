from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from kurrentscholar.constants import APP_NAME, default_log_dir

LOG_FILE_NAME = "kurrentscholar.log"


def log_path() -> Path:
    return default_log_dir() / LOG_FILE_NAME


def configure_logging() -> Path:
    destination = log_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger(APP_NAME)
    if not root.handlers:
        handler = RotatingFileHandler(
            destination,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
    return destination


def configure_network_trust() -> None:
    """Use the operating-system trust store, including institutional CAs."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        logging.getLogger(APP_NAME).warning(
            "Could not activate the operating-system certificate store", exc_info=True
        )


def install_exception_hook() -> None:
    logger = logging.getLogger(APP_NAME)
    previous = sys.excepthook

    def handle(exception_type, exception, exception_traceback) -> None:
        logger.critical(
            "Unhandled application exception\n%s",
            "".join(traceback.format_exception(exception_type, exception, exception_traceback)),
        )
        previous(exception_type, exception, exception_traceback)

    sys.excepthook = handle

