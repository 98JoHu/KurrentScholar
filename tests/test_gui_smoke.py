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

