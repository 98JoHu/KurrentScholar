from __future__ import annotations

import argparse
import os
import sys

from kurrentscholar import __version__


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    arguments, qt_arguments = parser.parse_known_args()
    if arguments.version:
        print(__version__)
        return 0
    if arguments.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from kurrentscholar.ui.main_window import MainWindow

    application = QApplication([sys.argv[0], *qt_arguments])
    application.setApplicationName("KurrentScholar")
    application.setOrganizationName("KurrentScholar")
    window = MainWindow()
    if arguments.smoke_test:
        window.close()
        print("KurrentScholar startup smoke test passed")
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

