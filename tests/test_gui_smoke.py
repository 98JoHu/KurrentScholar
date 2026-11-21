from types import SimpleNamespace

import pytest


@pytest.mark.gui
def test_main_window_starts(qtbot):
    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    assert window.windowTitle() == "KurrentScholar"
    assert window.menuBar().actions()
    assert "Transcribe current page" in window.actions
    assert "Transcribe page range…" in window.actions
    assert "Model Manager" in window.actions


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


@pytest.mark.gui
def test_resegmentation_creates_backup_before_reset(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    from kurrentscholar.domain import BoundingBox
    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import MainWindow

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project_path = tmp_path / "research.ksproj"
    project = ProjectDatabase(project_path, create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)
    project.add_line(1, 0, BoundingBox(10, 20, 300, 40), "old result", 0.8, [], [])

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    window.project_path = project_path
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.Yes)

    assert window._backup_and_reset_transcription("Detector changed.")
    assert project.lines() == []
    backups = list(tmp_path.glob("research.before-resegment-*.ksproj"))
    assert len(backups) == 1
    with ProjectDatabase(backups[0]) as backup:
        assert backup.lines()[0].machine_text == "old result"

