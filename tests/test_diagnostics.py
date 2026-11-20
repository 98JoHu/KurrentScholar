from __future__ import annotations

import logging
import time

from kurrentscholar.diagnostics import GuiWatchdog, exception_details


def test_exception_details_does_not_require_source_lookup():
    try:
        raise RuntimeError("pipeline failure")
    except RuntimeError as error:
        details = exception_details(error)

    assert "RuntimeError: pipeline failure" in details
    assert "test_exception_details_does_not_require_source_lookup" in details


def test_gui_watchdog_records_thread_stacks(caplog):
    caplog.set_level(logging.CRITICAL, logger="KurrentScholar.watchdog")
    watchdog = GuiWatchdog(timeout_seconds=0.03, check_interval=0.01)
    watchdog.start()
    try:
        deadline = time.monotonic() + 1
        while "GUI event loop has not responded" not in caplog.text and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        watchdog.stop()

    assert "GUI event loop has not responded" in caplog.text
    assert "Thread" in caplog.text
