from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from kurrentscholar import __version__
from kurrentscholar.constants import APP_NAME
from kurrentscholar.diagnostics import (
    configure_logging,
    configure_network_trust,
    install_exception_hook,
)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--install-model", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--model-smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--model-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help=argparse.SUPPRESS)
    arguments, qt_arguments = parser.parse_known_args()
    log_file = configure_logging()
    configure_network_trust()
    install_exception_hook()
    logger = logging.getLogger(APP_NAME)
    if arguments.version:
        print(__version__)
        return 0
    if arguments.install_model or arguments.model_smoke_test:
        from PIL import Image, ImageDraw

        from kurrentscholar.recognition import ModelManager, TrOCRBackend

        report: dict[str, object] = {
            "version": __version__,
            "log_file": str(log_file),
            "success": False,
        }
        try:
            manager = ModelManager(arguments.model_dir)
            if arguments.install_model:
                manager.install(lambda message: logger.info("Model installer: %s", message))
            status = manager.status()
            report.update({
                "model_path": str(status.path),
                "installed": status.installed,
                "missing_files": status.missing_files,
                "invalid_files": status.invalid_files,
            })
            if arguments.model_smoke_test:
                if not status.installed:
                    raise RuntimeError("The model is not installed and verified")
                image = Image.new("RGB", (900, 90), "white")
                ImageDraw.Draw(image).text((20, 25), "KurrentScholar model test 1874", fill="black")
                result = TrOCRBackend(status.path).recognize_line(image)
                report.update({
                    "generated_characters": len(result.text),
                    "scored_tokens": len(result.token_probabilities),
                })
            report["success"] = True
            exit_code = 0
        except Exception as error:
            logger.exception("Packaged model diagnostic failed")
            report["error"] = f"{error.__class__.__name__}: {error}"
            exit_code = 2
        if arguments.report:
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        else:
            print(json.dumps(report, indent=2))
        return exit_code
    if arguments.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from kurrentscholar.ui.main_window import MainWindow

    application = QApplication([sys.argv[0], *qt_arguments])
    application.setApplicationName("KurrentScholar")
    application.setOrganizationName("KurrentScholar")
    window = MainWindow(offer_model_on_startup=not arguments.smoke_test)
    if arguments.smoke_test:
        window.close()
        print("KurrentScholar startup smoke test passed")
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

