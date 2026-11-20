from types import SimpleNamespace

import pytest


@pytest.mark.gui
def test_main_window_starts(qtbot):
    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    assert window.windowTitle() == "KurrentScholar"


@pytest.mark.gui
def test_first_launch_offers_required_model(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.model_manager.root = tmp_path / "missing-model"
    started = []
    monkeypatch.setattr(window, "_start_model_installation", lambda: started.append(True))
    monkeypatch.setattr(QMessageBox, "exec", lambda _dialog: QMessageBox.Yes)
    window._offer_model_installation()
    assert started == [True]


@pytest.mark.gui
def test_model_completion_is_delivered_on_gui_thread(qtbot, monkeypatch):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QMessageBox

    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)

    def install(progress):
        progress("Verifying model integrity…")

    completion_threads = []

    def information(*_args, **_kwargs):
        completion_threads.append(QThread.currentThread() is window.thread())
        return QMessageBox.Ok

    monkeypatch.setattr(window.model_manager, "install", install)
    monkeypatch.setattr(
        window.model_manager,
        "status",
        lambda: SimpleNamespace(installed=True, missing_files=(), invalid_files=()),
    )
    monkeypatch.setattr(QMessageBox, "information", information)
    window._start_model_installation()
    qtbot.waitUntil(lambda: window._install_thread is None, timeout=5_000)

    assert completion_threads == [True]
    assert window._install_progress is None
    assert window.actions["Install model"].isEnabled()


@pytest.mark.gui
def test_model_failure_is_delivered_on_gui_thread(qtbot, monkeypatch):
    from PySide6.QtCore import QThread

    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)

    def install(_progress):
        raise RuntimeError("diagnostic failure")

    failures = []

    def error(title, message, details=""):
        failures.append((QThread.currentThread() is window.thread(), title, message, details))

    monkeypatch.setattr(window.model_manager, "install", install)
    monkeypatch.setattr(window, "_error", error)
    window._start_model_installation()
    qtbot.waitUntil(lambda: window._install_thread is None, timeout=5_000)

    assert failures
    assert failures[0][0] is True
    assert "diagnostic failure" in failures[0][2]
    assert window._install_progress is None
    assert window.actions["Install model"].isEnabled()

