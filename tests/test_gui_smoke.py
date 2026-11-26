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
    assert "Go to page…" in window.actions
    assert window.actions["Auto Save"].isCheckable()
    top_level_menus = [item.text().replace("&", "") for item in window.menuBar().actions()]
    assert "Export" in top_level_menus
    toolbar_text = {
        item.text() for toolbar in window.findChildren(__import__("PySide6.QtWidgets", fromlist=["QToolBar"]).QToolBar)
        for item in toolbar.actions()
    }
    assert "Export" not in toolbar_text
    assert "Save" not in toolbar_text
    assert window.review_splitter.orientation().name == "Vertical"


@pytest.mark.gui
def test_shortcuts_are_unique_and_avoid_macos_reserved_keys(qtbot):
    from PySide6.QtGui import QKeySequence

    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    owners: dict[str, str] = {}
    for name, action in window.actions.items():
        for sequence in action.shortcuts():
            text = sequence.toString(QKeySequence.PortableText)
            # Two actions sharing one sequence make Qt trigger neither of them.
            assert owners.setdefault(text, name) == name, f"{text}: {owners[text]} and {name}"
            primary = action.shortcuts()[0].toString(QKeySequence.PortableText)
            # Ctrl maps to Cmd on macOS, where Cmd+Space opens Spotlight.
            assert primary != "Ctrl+Space"
            # Bare F-keys require Fn on Mac keyboards, so they may only be secondary.
            assert not (primary.startswith("F") and primary[1:].isdigit())


@pytest.mark.gui
def test_spin_box_arrow_images_exist(qtbot):
    import re
    from pathlib import Path

    from kurrentscholar.ui.main_window import MainWindow

    paths = re.findall(r'url\("([^"]+)"\)', MainWindow._spin_arrow_style())
    assert len(paths) == 4
    assert all(Path(path).is_file() for path in paths)


@pytest.mark.gui
def test_tutorial_starts_with_welcome_then_points_to_real_controls(qtbot):
    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.show()
    window._start_tutorial(first_run=False)

    overlay = window._tutorial_overlay
    assert overlay is not None
    assert overlay.heading.text() == "Welcome to KurrentScholar"
    assert overlay.steps[0][2] is None
    overlay._move(1)
    assert overlay.steps[1][2] is window._tutorial_targets["open"]
    overlay.close_tour()


@pytest.mark.gui
def test_tutorial_fits_small_windows_and_does_not_cover_its_target(qtbot):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget

    from kurrentscholar.ui.dialogs import TutorialOverlay

    parent = QWidget()
    parent.resize(740, 425)
    qtbot.addWidget(parent)
    target = QWidget(parent)
    target.setGeometry(QRect(500, 55, 210, 335))
    target.show()
    parent.show()

    # Long enough to overflow the 425 px window with any platform's font metrics.
    long_text = " ".join(
        [
            "KurrentScholar keeps every part of this explanation available on smaller screens."
            for _ in range(40)
        ]
    )
    overlay = TutorialOverlay(
        [
            ("Welcome to KurrentScholar", long_text, None),
            ("Review the transcription", "This panel remains visible beside the explanation.", target),
        ],
        parent,
    )
    overlay.show()
    qtbot.wait(50)

    assert overlay.rect().contains(overlay.card.geometry())
    scroll_bar = overlay.body_scroll.verticalScrollBar()
    # Scroll ranges are applied from queued layout events, later on some platforms (macOS).
    qtbot.waitUntil(lambda: scroll_bar.maximum() > 0, timeout=2_000)
    # Every line of the explanation must remain reachable by scrolling.
    body = overlay.body
    assert body.height() >= body.heightForWidth(body.width())
    assert overlay.body_scroll.viewport().height() + scroll_bar.maximum() >= body.height()

    overlay._move(1)
    qtbot.wait(20)
    highlighted = overlay._target_rect()
    assert highlighted is not None
    assert not overlay.card.geometry().intersects(highlighted)
    assert overlay.rect().contains(overlay.card.geometry())
    overlay.close_tour()


@pytest.mark.gui
def test_live_boxes_use_stored_detection_scale_immediately(qtbot, tmp_path):
    from PySide6.QtGui import QPixmap

    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import MainWindow

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project = ProjectDatabase(tmp_path / "scale.ksproj", create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    window.pixmap_item.setPixmap(QPixmap(500, 750))
    window._sync_display_scale_from_project_page()

    assert window._display_scale_x == pytest.approx(0.5)
    assert window._display_scale_y == pytest.approx(0.5)


@pytest.mark.gui
def test_hovering_transcription_highlights_matching_box(qtbot, tmp_path):
    from PySide6.QtGui import QPixmap

    from kurrentscholar.domain import BoundingBox
    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import MainWindow

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project = ProjectDatabase(tmp_path / "hover.ksproj", create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)
    line_id = project.add_line(1, 0, BoundingBox(10, 20, 300, 40), "result", 0.8, [], [])

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    window.pixmap_item.setPixmap(QPixmap(500, 750))
    window._sync_display_scale_from_project_page()
    window._refresh_lines()
    window._hover_line(line_id)

    overlay = next(item for item in window._overlays if item.data(0) == line_id)
    assert overlay.brush().color().alpha() > 0
    assert overlay.pen().width() == 3


@pytest.mark.gui
def test_live_line_refresh_keeps_reviewer_caret_and_edit(qtbot, tmp_path):
    from kurrentscholar.domain import BoundingBox
    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import MainWindow

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project = ProjectDatabase(tmp_path / "live.ksproj", create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)
    line_id = project.add_line(1, 0, BoundingBox(10, 20, 300, 40), "erste Zeile", 0.8, [], [])

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    window._refresh_lines()
    window.line_list.setCurrentRow(0)
    cursor = window.editor.textCursor()
    cursor.setPosition(5)
    window.editor.setTextCursor(cursor)
    window.editor.insertPlainText("!")

    # A new line arriving from the transcription worker triggers a list refresh.
    project.add_line(1, 1, BoundingBox(10, 80, 300, 40), "zweite Zeile", 0.8, [], [])
    window._processing_line_saved(1, 0)

    assert window.current_line_id == line_id
    assert window.editor.toPlainText() == "erste! Zeile"
    assert window.editor.textCursor().position() == 6
    assert project.line(line_id).display_text == "erste! Zeile"


@pytest.mark.gui
def test_rich_corrections_persist_unicode_superscript_and_tags(qtbot, tmp_path):
    from PySide6.QtGui import QTextCursor

    from kurrentscholar.domain import BoundingBox
    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import (
        TAG_COLOR_PROPERTY,
        TAG_PROPERTY,
        MainWindow,
    )

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project = ProjectDatabase(tmp_path / "annotations.ksproj", create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)
    line_id = project.add_line(
        1, 0, BoundingBox(10, 20, 300, 40), "Straße H2O §", 0.8, [], []
    )

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    window._refresh_lines()
    window.line_list.setCurrentRow(0)

    cursor = window.editor.textCursor()
    cursor.setPosition(8)
    cursor.setPosition(9, QTextCursor.KeepAnchor)
    window.editor.setTextCursor(cursor)
    window._toggle_vertical_format("subscript")

    cursor.setPosition(0)
    cursor.setPosition(6, QTextCursor.KeepAnchor)
    formatting = cursor.charFormat()
    formatting.setProperty(TAG_PROPERTY, "Person")
    formatting.setProperty(TAG_COLOR_PROPERTY, "#F2C7C3")
    cursor.mergeCharFormat(formatting)
    window.save_current_edit()

    stored = project.line(line_id)
    assert stored.display_text == "Straße H2O §"
    assert any(item["kind"] == "subscript" for item in stored.annotations)
    assert any(item.get("label") == "Person" for item in stored.annotations)


@pytest.mark.gui
def test_direct_page_navigation_updates_current_page(qtbot, monkeypatch, tmp_path):
    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import MainWindow

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project = ProjectDatabase(tmp_path / "pages.ksproj", create=True)
    project.set_document(source, 4)

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    monkeypatch.setattr(window, "_render_page", lambda: window._update_navigation_actions())
    monkeypatch.setattr(window, "_refresh_lines", lambda *args, **kwargs: None)
    window._go_to_page(3)

    assert window.current_page == 3
    assert window.page_selector.value() == 3


@pytest.mark.gui
def test_autosave_defaults_on_and_can_be_disabled(qtbot, monkeypatch):
    import kurrentscholar.ui.main_window as main_window

    values = {}

    class FakeSettings:
        def value(self, key, default=None, type=None):
            value = values.get(key, default)
            return type(value) if type else value

        def setValue(self, key, value):
            values[key] = value

    monkeypatch.setattr(main_window, "QSettings", FakeSettings)
    window = main_window.MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)

    assert window.autosave_enabled is True
    assert window.actions["Auto Save"].isChecked()
    window.actions["Auto Save"].trigger()
    assert window.autosave_enabled is False
    assert values["editor/autosave"] is False


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
    assert window.actions["Model Manager"].isEnabled()


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
    assert window.actions["Model Manager"].isEnabled()


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



@pytest.mark.gui
def test_install_completion_checks_the_downloaded_model_not_a_later_selection(qtbot, monkeypatch):
    import threading

    from PySide6.QtWidgets import QMessageBox

    from kurrentscholar.constants import MODEL_CATALOG
    from kurrentscholar.recognition import ModelManager
    from kurrentscholar.ui.main_window import MainWindow

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    release = threading.Event()
    downloading = window.model_manager
    monkeypatch.setattr(downloading, "install", lambda _progress: release.wait(5))
    monkeypatch.setattr(
        downloading,
        "status",
        lambda: SimpleNamespace(installed=True, missing_files=(), invalid_files=()),
    )
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **_: messages.append(args[1]))
    errors = []
    monkeypatch.setattr(window, "_error", lambda title, *_: errors.append(title))

    window._start_model_installation()
    # Something else (e.g. starting a transcription) switches the project model meanwhile.
    window.model_manager = ModelManager(spec=MODEL_CATALOG[1])
    window._install_selected_model(MODEL_CATALOG[2])
    assert errors == ["A model download is active"]
    release.set()
    qtbot.waitUntil(lambda: window._install_thread is None, timeout=5_000)

    assert errors == ["A model download is active"]
    assert messages == ["Model installation complete"]


@pytest.mark.gui
def test_review_list_marks_verified_lines_and_skips_them(qtbot, tmp_path):
    from kurrentscholar.domain import BoundingBox, ReviewStatus
    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import MainWindow

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project = ProjectDatabase(tmp_path / "review.ksproj", create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)
    first = project.add_line(1, 0, BoundingBox(10, 20, 300, 40), "eins", 0.6, [], [])
    project.add_line(1, 1, BoundingBox(10, 80, 300, 40), "zwei", 0.95, [], [])
    third = project.add_line(1, 2, BoundingBox(10, 140, 300, 40), "drei", 0.6, [], [])
    project.add_line(
        1, 3, BoundingBox(10, 200, 300, 40), "", None, [], [], recognition_error="boom"
    )
    project.set_review_status(third, ReviewStatus.VERIFIED)

    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    window.project_path = tmp_path / "review.ksproj"
    window._refresh_lines()

    assert "✓" in window.line_list.item(2).text()
    assert "Recognition failed: boom" in window.line_list.item(3).toolTip()
    window.line_list.setCurrentRow(0)
    window._next_uncertain()
    assert window.line_list.currentRow() == 3  # skips confident line 2 and verified line 3

    window.line_list.setCurrentRow(0)
    window._verify_line()
    assert window.current_line_id == first
    assert "✓" in window.line_list.item(0).text()
    assert window._export_default_path(".txt") == str(tmp_path / "review.txt")
