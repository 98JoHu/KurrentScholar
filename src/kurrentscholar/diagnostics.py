from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from kurrentscholar.constants import APP_NAME, default_log_dir

LOG_FILE_NAME = "kurrentscholar.log"
CRASH_LOG_FILE_NAME = "kurrentscholar-crash.log"
_crash_stream = None


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


def configure_crash_logging() -> Path:
    """Capture fatal Python/native failures and all thread stacks in a separate file."""
    global _crash_stream
    destination = default_log_dir() / CRASH_LOG_FILE_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _crash_stream is None:
        _crash_stream = destination.open("a", encoding="utf-8")
        faulthandler.enable(_crash_stream, all_threads=True)
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
        if sys.stderr is not None:
            previous(exception_type, exception, exception_traceback)

    sys.excepthook = handle

    previous_thread_hook = threading.excepthook

    def handle_thread(args: threading.ExceptHookArgs) -> None:
        logger.critical(
            "Unhandled exception in thread %s\n%s",
            args.thread.name if args.thread else "unknown",
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )
        if sys.stderr is not None:
            previous_thread_hook(args)

    threading.excepthook = handle_thread


def exception_details(error: BaseException) -> str:
    """Format a traceback without asking linecache to read source files.

    This remains reliable in frozen builds and in Windows cloud-synced folders where source lookup can
    itself fail while an original exception is being handled.
    """
    frames = []
    current = error.__traceback__
    while current is not None:
        code = current.tb_frame.f_code
        frames.append(f'  File "{code.co_filename}", line {current.tb_lineno}, in {code.co_name}')
        current = current.tb_next
    prefix = "Traceback (most recent call last):\n" + "\n".join(frames) + "\n" if frames else ""
    return f"{prefix}{error.__class__.__name__}: {error}"


def install_qt_message_handler() -> None:
    """Route Qt warnings and fatal messages into the persistent application log."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handle(message_type, context, message) -> None:
        location = ""
        if context and context.file:
            location = f" ({context.file}:{context.line})"
        logging.getLogger(f"{APP_NAME}.qt").log(
            levels.get(message_type, logging.WARNING), "Qt: %s%s", message, location
        )

    qInstallMessageHandler(handle)


class GuiWatchdog:
    """Record all thread stacks once if the Qt event loop stops responding."""

    def __init__(self, timeout_seconds: float = 15.0, check_interval: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.check_interval = check_interval
        self._last_pulse = time.monotonic()
        self._reported = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="KurrentScholar GUI watchdog",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def pulse(self) -> None:
        with self._lock:
            recovered = self._reported
            self._last_pulse = time.monotonic()
            self._reported = False
        if recovered:
            logging.getLogger(f"{APP_NAME}.watchdog").info("GUI event loop recovered")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.check_interval):
            with self._lock:
                stalled_for = time.monotonic() - self._last_pulse
                should_report = stalled_for >= self.timeout_seconds and not self._reported
                if should_report:
                    self._reported = True
            if should_report:
                logging.getLogger(f"{APP_NAME}.watchdog").critical(
                    "GUI event loop has not responded for %.1f seconds\n%s",
                    stalled_for,
                    self._thread_dump(),
                )

    @staticmethod
    def _thread_dump() -> str:
        names = {thread.ident: thread.name for thread in threading.enumerate()}
        sections = []
        for identifier, frame in sys._current_frames().items():
            name = names.get(identifier, "unknown")
            sections.append(
                f"--- Thread {name} ({identifier}) ---\n{''.join(traceback.format_stack(frame))}"
            )
        return "\n".join(sections)

