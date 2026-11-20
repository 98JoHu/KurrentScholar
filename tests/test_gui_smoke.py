import pytest


@pytest.mark.gui
def test_main_window_starts(qtbot):
    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "KurrentScholar"

