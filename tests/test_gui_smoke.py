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


def _tag_window(qtbot, tmp_path, texts):
    from kurrentscholar.domain import BoundingBox
    from kurrentscholar.projects import ProjectDatabase
    from kurrentscholar.ui.main_window import MainWindow

    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    project = ProjectDatabase(tmp_path / "tags.ksproj", create=True)
    project.set_document(source, 1)
    project.upsert_page(1, 1000, 1500, 300)
    ids = [
        project.add_line(1, index, BoundingBox(10, 20 + 60 * index, 300, 40), text, 0.95, [], [])
        for index, text in enumerate(texts)
    ]
    window = MainWindow(offer_model_on_startup=False)
    qtbot.addWidget(window)
    window.project = project
    window.project_path = tmp_path / "tags.ksproj"
    window._refresh_lines()
    return window, project, ids


def _place_caret(window, start, end=None):
    from PySide6.QtGui import QTextCursor

    cursor = window.editor.textCursor()
    cursor.setPosition(start)
    if end is not None:
        cursor.setPosition(end, QTextCursor.KeepAnchor)
    window.editor.setTextCursor(cursor)


@pytest.mark.gui
def test_tag_is_named_at_its_word_in_list_editor_panel_and_tooltip(qtbot, tmp_path):
    from kurrentscholar.ui.main_window import LINE_HTML_ROLE

    window, project, (line_id,) = _tag_window(qtbot, tmp_path, ["Matthias Müller zu Wien"])
    window.line_list.setCurrentRow(0)
    _place_caret(window, 11)  # inside "Müller": the word at the caret is tagged
    window._apply_tag("Person")
    window.save_current_edit()

    stored = project.line(line_id)
    assert [(a["label"], a["start"], a["end"]) for a in stored.annotations if a["kind"] == "tag"] == [
        ("Person", 9, 15)
    ]
    markup = window.line_list.item(0).data(LINE_HTML_ROLE)
    assert markup.index("Müller") < markup.index("Person") < markup.index("zu Wien")
    assert "Tags: Person: Müller" in window.line_list.item(0).toolTip()
    assert "Person" in window.tag_panel.text() and "Müller" in window.tag_panel.text()
    assert window._project_tag_colors()["Person"]


@pytest.mark.gui
def test_typing_after_a_tag_does_not_extend_it_but_corrections_inside_do(qtbot, tmp_path):
    window, project, (line_id,) = _tag_window(qtbot, tmp_path, ["Matthias Müller zu Wien"])
    window.line_list.setCurrentRow(0)
    _place_caret(window, 9, 15)
    window._apply_tag("Person")
    _place_caret(window, 15)
    qtbot.keyClicks(window.editor, " sen.")  # typed on the keyboard
    _place_caret(window, 12)
    window.editor.insertPlainText("l")  # "Mülller" correction within the name
    window.save_current_edit()

    tags = [a for a in project.line(line_id).annotations if a["kind"] == "tag"]
    assert [(a["start"], a["end"]) for a in tags] == [(9, 16)]
    assert project.line(line_id).display_text == "Matthias Mülller sen. zu Wien"


@pytest.mark.gui
def test_selecting_another_line_never_copies_formatting_onto_it(qtbot, tmp_path):
    window, project, (tagged, plain) = _tag_window(qtbot, tmp_path, ["zu Wien", "ganz andere Zeile"])
    project.correct_line(
        tagged, "zu Wien", [{"start": 3, "end": 7, "kind": "tag", "label": "Place", "color": "#C9DDF7"}]
    )
    window.line_list.setCurrentRow(0)
    _place_caret(window, 5)  # caret inside the tagged place name
    window.line_list.setCurrentRow(1)
    window.line_list.setCurrentRow(0)

    assert project.line(plain).annotations == []
    assert window.line_list.currentRow() == 0


@pytest.mark.gui
def test_clear_format_and_tag_removal_really_remove_formatting(qtbot, tmp_path):
    window, project, (line_id,) = _tag_window(qtbot, tmp_path, ["Matthias Müller zu Wien"])
    project.correct_line(line_id, "Matthias Müller zu Wien", [
        {"start": 9, "end": 15, "kind": "tag", "label": "Person", "color": "#F2C7C3"},
        {"start": 19, "end": 23, "kind": "highlight", "color": "#FFF0A8"},
        {"start": 0, "end": 2, "kind": "superscript"},
    ])
    window._refresh_lines()
    window.line_list.setCurrentRow(0)

    # A highlight under a tag survives tagging and later removal of that tag.
    _place_caret(window, 19, 23)
    window._apply_tag("Place")
    window._tag_panel_link("remove:1")
    window.save_current_edit()
    kinds = {(a["kind"], a.get("label")) for a in project.line(line_id).annotations}
    assert ("highlight", None) in kinds and ("tag", "Place") not in kinds
    assert ("tag", "Person") in kinds

    _place_caret(window, 0, len("Matthias Müller zu Wien"))
    window._clear_selection_format()
    window.save_current_edit()
    assert project.line(line_id).annotations == []


@pytest.mark.gui
def test_tag_overview_lists_tags_and_jumps_to_the_tagged_words(qtbot, tmp_path):
    window, project, (first, second) = _tag_window(qtbot, tmp_path, ["Matthias Müller", "zu Wien"])
    project.correct_line(second, "zu Wien", [{"start": 3, "end": 7, "kind": "tag", "label": "Place"}])
    project.correct_line(first, "Matthias Müller", [{"start": 0, "end": 15, "kind": "tag", "label": "Pfarrer"}])
    window.show_tag_overview()
    dialog = window._tag_overview
    assert dialog is not None
    assert dialog.table.rowCount() == 2
    assert "Pfarrer" in window._tag_choices()  # custom labels are offered again

    dialog.search.setText("wien")
    assert dialog.table.rowCount() == 1
    dialog._jump()
    assert window.current_line_id == second
    assert window.editor.textCursor().selectedText() == "Wien"
    dialog.close()
    assert window._tag_overview is None


@pytest.mark.gui
def test_reading_order_moves_persist_and_number_the_list_and_page(qtbot, tmp_path):
    window, project, (first, second, third) = _tag_window(
        qtbot, tmp_path, ["forderung und Gegen", "Aul. No 1-6", "forderung betreffend"]
    )
    window.line_list.setCurrentRow(2)
    window.actions["Move line up"].trigger()

    assert [line.id for line in project.lines(1)] == [first, third, second]
    assert window.current_line_id == third
    assert window.line_list.currentRow() == 1
    assert window.line_list.item(1).text().startswith("002")
    badges = {
        overlay.data(0): overlay.childItems()[0].childItems()[0].text()
        for overlay in window._overlays
    }
    assert badges == {first: "1", third: "2", second: "3"}

    # A drag-and-drop reorder stores whatever order the list shows.
    item = window.line_list.takeItem(0)
    window.line_list.insertItem(2, item)
    window._store_list_order()
    assert [line.id for line in project.lines(1)] == [third, second, first]

    window.actions["Restore detected order"].trigger()
    assert [line.id for line in project.lines(1)] == [first, second, third]

    window._set_show_reading_order(False)
    assert all(not overlay.childItems() for overlay in window._overlays)
