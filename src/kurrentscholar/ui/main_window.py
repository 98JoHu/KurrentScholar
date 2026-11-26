from __future__ import annotations

import html
import json
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from statistics import median

from PIL.ImageQt import ImageQt
from PySide6.QtCore import (
    QEvent,
    QObject,
    QPointF,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QAction,
    QBrush,
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QToolBar,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from kurrentscholar import __version__
from kurrentscholar.annotations import (
    HIGHLIGHT_COLOR,
    TAG_COLORS,
    TagSpan,
    annotated_html,
    custom_tag_color,
    tag_color,
    tag_label_html,
    tag_spans,
    tag_summary,
    tag_text_color,
)
from kurrentscholar.constants import (
    APP_NAME,
    DEFAULT_MODEL,
    MODEL_CATALOG,
    ModelSpec,
    find_model,
)
from kurrentscholar.diagnostics import CRASH_LOG_FILE_NAME, exception_details, log_path
from kurrentscholar.document_processing import DocumentRenderer, PageRangeError, parse_page_range
from kurrentscholar.domain import ConfidenceThresholds, ReviewStatus
from kurrentscholar.evaluation import evaluate_project_lines
from kurrentscholar.exports import (
    export_csv,
    export_docx,
    export_json,
    export_text,
    export_xlsx,
)
from kurrentscholar.ground_truth import GroundTruthError, export_training_bundle
from kurrentscholar.projects import ProjectDatabase
from kurrentscholar.recognition import ModelManager, TrOCRBackend
from kurrentscholar.segmentation import ProjectionSegmenter
from kurrentscholar.ui.dialogs import (
    GroundTruthDialog,
    ModelManagerDialog,
    TagOverviewDialog,
    TutorialOverlay,
)

LOGGER = logging.getLogger(f"{APP_NAME}.ui")

TAG_PROPERTY = QTextFormat.UserProperty + 1
TAG_COLOR_PROPERTY = QTextFormat.UserProperty + 2
HIGHLIGHT_PROPERTY = QTextFormat.UserProperty + 3
NEEDS_REVIEW_ROLE = Qt.UserRole + 1
LINE_HTML_ROLE = Qt.UserRole + 2
CONFIDENCE_COLORS = {
    "moderate": "#FFF0C2",
    "high_uncertainty": "#F7D8C4",
    "very_high_uncertainty": "#F2B8B5",
    "unavailable": "#E5E8EB",
}
# Qt maps "Ctrl" to the Command key on macOS. Shortcuts avoid keys that are reserved
# by macOS (Cmd+Space), need Fn on Mac keyboards (F-keys), or need Shift on German
# layouts ("="). The first sequence is shown in menus and tooltips; later ones are
# retained so earlier habits keep working where the platform allows them.
SHORTCUTS: dict[str, tuple[str, ...]] = {
    "superscript": ("Ctrl+.", "Ctrl+Shift+="),
    "subscript": ("Ctrl+,", "Ctrl+="),
    "clear_format": ("Ctrl+Shift+Space", "Ctrl+Space"),
    "next_uncertain": ("Ctrl+Shift+N", "F6"),
    "tag": ("Ctrl+Shift+G",),
    # Alt (Option) with the arrows is unused by text fields on Windows and macOS.
    "move_line_up": ("Alt+Up",),
    "move_line_down": ("Alt+Down",),
}


def shortcut_text(sequence: str | QKeySequence.StandardKey) -> str:
    """Render a shortcut the way the platform displays it (Ctrl+S or ⌘S)."""

    return QKeySequence(sequence).toString(QKeySequence.NativeText)


SPECIAL_CHARACTERS = (
    "ä", "ö", "ü", "Ä", "Ö", "Ü", "ß", "ẞ", "ſ", "æ", "Æ", "œ", "Œ",
    "§", "¶", "†", "‡", "°", "№", "½", "¼", "¾", "–", "—", "…",
)


class LineListWidget(QListWidget):
    """Line list that reports hover changes and lets reviewers drag lines into reading order."""

    line_hovered = Signal(object)
    order_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._last_hovered_id: int | None = None
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        # Rows wrap so the whole line, including its tag names, stays readable.
        self.setWordWrap(True)
        self.setResizeMode(QListView.Adjust)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(LineItemDelegate(self))

    def dropEvent(self, event) -> None:
        if event.source() is not self:
            event.ignore()
            return
        super().dropEvent(event)
        # Rebuilding the list inside the drag's own event handling is unsafe; store the
        # new order once the drop has fully completed.
        QTimer.singleShot(0, self.order_changed.emit)

    def mouseMoveEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        line_id = int(item.data(Qt.UserRole)) if item else None
        if line_id != self._last_hovered_id:
            self._last_hovered_id = line_id
            self.line_hovered.emit(line_id)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._last_hovered_id is not None:
            self._last_hovered_id = None
            self.line_hovered.emit(None)
        super().leaveEvent(event)


class LineItemDelegate(QStyledItemDelegate):
    """Draws a listed line as rich text so tags appear, named, at their words."""

    def _document(self, option: QStyleOptionViewItem, markup: str, width: int) -> QTextDocument:
        document = QTextDocument()
        document.setDefaultFont(option.font)
        document.setHtml(f'<p style="margin:0; white-space:pre-wrap;">{markup}</p>')
        document.setTextWidth(max(80, width))
        return document

    def _width(self, option: QStyleOptionViewItem) -> int:
        view = self.parent()
        if isinstance(view, QListWidget):
            return view.viewport().width() - 2 * view.spacing() - 2
        return option.rect.width()

    def sizeHint(self, option, index) -> QSize:
        markup = index.data(LINE_HTML_ROLE)
        if not markup:
            return super().sizeHint(option, index)
        width = self._width(option)
        document = self._document(option, markup, width)
        return QSize(width, int(document.size().height()) + 2)

    def paint(self, painter, option, index) -> None:
        markup = index.data(LINE_HTML_ROLE)
        if not markup:
            super().paint(painter, option, index)
            return
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        widget = styled.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, styled, painter, widget)
        document = self._document(styled, markup, styled.rect.width())
        painter.save()
        painter.translate(styled.rect.topLeft())
        painter.setClipRect(QRectF(0, 0, styled.rect.width(), styled.rect.height()))
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.Text, QColor("#20252B"))
        document.documentLayout().draw(painter, context)
        painter.restore()


class TranscriptionEditor(QTextEdit):
    """Line editor that names tags on hover and keeps tags on the words they were given to.

    Qt gives newly typed text the format of the character before the caret, so typing
    right after a tagged name would silently extend the tag to the next word.
    """

    context_menu_extender = None  # callable(menu, cursor) installed by the main window

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cursorPositionChanged.connect(self._end_tag_at_caret)

    @staticmethod
    def _tag_at(cursor: QTextCursor) -> str | None:
        formatting = cursor.charFormat()
        return str(formatting.property(TAG_PROPERTY)) if formatting.hasProperty(TAG_PROPERTY) else None

    def _end_tag_at_caret(self) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        label = self._tag_at(cursor)
        if label is None:
            return
        following = QTextCursor(cursor)
        if not following.atBlockEnd():
            following.movePosition(QTextCursor.NextCharacter)
            if self._tag_at(following) == label:
                return  # inside the tagged words: corrections stay part of the tag
        self.setCurrentCharFormat(untagged_format(cursor.charFormat()))

    # Re-placing the caret without moving it resets the insertion format without a
    # cursorPositionChanged signal, so every way of inserting text checks again.
    def keyPressEvent(self, event) -> None:
        if event.text() and event.text().isprintable():
            self._end_tag_at_caret()
        super().keyPressEvent(event)

    def inputMethodEvent(self, event) -> None:
        if event.commitString():
            self._end_tag_at_caret()
        super().inputMethodEvent(event)

    def insertFromMimeData(self, source) -> None:
        self._end_tag_at_caret()
        super().insertFromMimeData(source)

    def insertPlainText(self, text: str) -> None:
        self._end_tag_at_caret()
        super().insertPlainText(text)

    def prepare_insertion(self) -> None:
        self._end_tag_at_caret()

    def tag_under(self, position) -> str | None:
        cursor = self.cursorForPosition(position)
        label = self._tag_at(cursor)
        if label is None and not cursor.atBlockEnd():
            cursor.movePosition(QTextCursor.NextCharacter)
            label = self._tag_at(cursor)
        return label

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            label = self.tag_under(event.pos())
            if label:
                QToolTip.showText(event.globalPos(), f"Tag: {label}", self.viewport())
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().viewportEvent(event)

    def contextMenuEvent(self, event) -> None:
        cursor = self.textCursor()
        clicked = self.cursorForPosition(event.pos())
        inside_selection = (
            cursor.hasSelection()
            and cursor.selectionStart() <= clicked.position() <= cursor.selectionEnd()
        )
        if not inside_selection:
            # Act on the word that was right-clicked, as word processors do.
            self.setTextCursor(clicked)
            cursor = clicked
        menu = self.createStandardContextMenu(event.pos())
        if callable(self.context_menu_extender):
            self.context_menu_extender(menu, cursor)
        menu.exec(event.globalPos())
        menu.deleteLater()


def untagged_format(formatting: QTextCharFormat) -> QTextCharFormat:
    """Copy a character format without its tag (a highlight underneath stays visible)."""

    result = QTextCharFormat(formatting)
    result.clearProperty(TAG_PROPERTY)
    result.clearProperty(TAG_COLOR_PROPERTY)
    result.setFontUnderline(False)
    result.clearProperty(QTextFormat.TextUnderlineColor)
    if result.hasProperty(HIGHLIGHT_PROPERTY):
        result.setBackground(QColor(HIGHLIGHT_COLOR))
    else:
        result.clearBackground()
    return result


def tag_format(label: str, color: str) -> QTextCharFormat:
    formatting = QTextCharFormat()
    formatting.setBackground(QColor(color))
    # The underline keeps a tag visible while its words are selected.
    formatting.setFontUnderline(True)
    formatting.setUnderlineColor(QColor(tag_text_color(color)))
    formatting.setProperty(TAG_PROPERTY, label)
    formatting.setProperty(TAG_COLOR_PROPERTY, color)
    return formatting


class ProcessingWorker(QObject):
    progress = Signal(int, int, str)
    line_saved = Signal(int, int)
    finished = Signal(bool)
    failed = Signal(str, str)

    def __init__(
        self,
        project_path: Path,
        pages: list[int],
        model_path: Path,
        model_spec: ModelSpec,
        dpi: int = 300,
    ) -> None:
        super().__init__()
        self.project_path = project_path
        self.pages = pages
        self.model_path = model_path
        self.model_spec = model_spec
        self.dpi = dpi
        self.cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            LOGGER.info(
                "Transcription worker starting: project=%s pages=%s thread=%s",
                self.project_path,
                len(self.pages),
                threading.get_ident(),
            )
            with ProjectDatabase(self.project_path) as project:
                document = project.document()
                if not document:
                    raise ValueError("The project has no source document")
                renderer = DocumentRenderer()
                segmenter = ProjectionSegmenter()
                existing_summary = project.transcription_summary()
                stored_info = project.info()
                if existing_summary["line_count"] and (
                    stored_info.get("segmentation_backend") != segmenter.backend_id
                    or stored_info.get("segmentation_version") != segmenter.version
                ):
                    raise RuntimeError(
                        "This project contains results from an older line detector. "
                        "Open it in KurrentScholar and choose Re-segment so the existing "
                        "results are backed up before replacement."
                    )
                recognizer = TrOCRBackend(
                    self.model_path,
                    max_new_tokens=self.model_spec.max_new_tokens,
                )
                LOGGER.info("Loading recognition model from %s", self.model_path)
                recognizer.load()
                LOGGER.info("Recognition model loaded")
                project.set_info({
                    "model_id": self.model_spec.model_id,
                    "model_revision": self.model_spec.revision,
                    "segmentation_backend": segmenter.backend_id,
                    "segmentation_version": segmenter.version,
                })
                total = len(self.pages)
                for position, page_index in enumerate(self.pages, start=1):
                    if self.cancel_event.is_set():
                        break
                    self.progress.emit(position - 1, total, f"Rendering page {page_index + 1}")
                    rendered = renderer.render(document["source_path"], page_index, self.dpi)
                    LOGGER.info(
                        "Rendered page %s at %s DPI (%sx%s)",
                        page_index + 1,
                        self.dpi,
                        rendered.image.width,
                        rendered.image.height,
                    )
                    lines = segmenter.detect_lines(rendered.image)
                    LOGGER.info("Detected %s line(s) on page %s", len(lines), page_index + 1)
                    if lines:
                        heights = [line.bbox.height for line in lines]
                        typical_height = float(median(heights))
                        suspicious = [
                            height
                            for height in heights
                            if height > max(rendered.image.height * 0.10, typical_height * 3.5)
                        ]
                        if suspicious:
                            LOGGER.warning(
                                "Page %s has %s suspiciously tall crop(s): heights=%s, median=%.1f",
                                page_index + 1,
                                len(suspicious),
                                suspicious,
                                typical_height,
                            )
                    status = "segmented" if lines else "segmentation_failed"
                    error = None if lines else "No handwriting lines were detected; review this page manually."
                    project.upsert_page(
                        page_index + 1,
                        rendered.image.width,
                        rendered.image.height,
                        self.dpi,
                        deskew_angle=segmenter.last_deskew_angle,
                        status=status,
                        error=error,
                    )
                    existing = {
                        line.reading_order: line for line in project.lines(page_index + 1)
                    }
                    for line_number, detected in enumerate(lines):
                        if self.cancel_event.is_set():
                            break
                        prior = existing.get(detected.reading_order)
                        if prior and (prior.machine_text or prior.corrected_text is not None):
                            if prior.bbox != detected.bbox:
                                raise RuntimeError(
                                    f"Line detection changed unexpectedly on page {page_index + 1}. "
                                    "Use Re-segment to create a backup and replace the old results safely."
                                )
                            continue
                        self.progress.emit(position - 1, total,
                                           f"Page {page_index + 1}: line {line_number + 1}/{len(lines)}")
                        box = detected.bbox
                        crop = detected.crop or rendered.image.crop(
                            (box.x, box.y, box.right, box.bottom)
                        )
                        try:
                            LOGGER.info(
                                "Recognizing page %s line %s", page_index + 1, line_number + 1
                            )
                            result = recognizer.recognize_line(crop)
                            line_id = project.add_line(
                                page_index + 1, detected.reading_order, box, result.text,
                                result.line_confidence, result.token_probabilities,
                                result.token_ids, result.truncated,
                                polygon=list(detected.polygon),
                            )
                        except Exception as error:  # keep failed regions visible
                            LOGGER.error(
                                "Recognition failed on page %s line %s\n%s",
                                page_index + 1,
                                line_number + 1,
                                exception_details(error),
                            )
                            line_id = project.add_line(
                                page_index + 1, detected.reading_order, box, "", None, [], [],
                                recognition_error=str(error), polygon=list(detected.polygon),
                            )
                        self.line_saved.emit(page_index + 1, line_id)
                    self.progress.emit(position, total, f"Saved page {page_index + 1}")
            cancelled = self.cancel_event.is_set()
            LOGGER.info("Transcription worker finished: cancelled=%s", cancelled)
            self.finished.emit(cancelled)
        except Exception as error:
            details = exception_details(error)
            LOGGER.error("Transcription worker failed\n%s", details)
            self.failed.emit(str(error), details)

    def request_cancel(self) -> None:
        self.cancel_event.set()


class ModelInstallWorker(QObject):
    finished = Signal()
    failed = Signal(str, str)
    status = Signal(str)

    def __init__(self, manager: ModelManager) -> None:
        super().__init__()
        self.manager = manager

    @Slot()
    def run(self) -> None:
        try:
            LOGGER.info("Model installation worker starting: thread=%s", threading.get_ident())
            self.manager.install(self.status.emit)
            LOGGER.info("Model installation worker finished successfully")
            self.finished.emit()
        except Exception as error:
            details = exception_details(error)
            LOGGER.error("Model installation worker failed\n%s", details)
            self.failed.emit(str(error), details)


class MainWindow(QMainWindow):
    def __init__(self, offer_model_on_startup: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("KurrentScholar")
        self.resize(1280, 800)
        self.setAcceptDrops(True)
        self.renderer = DocumentRenderer()
        self.model_manager = ModelManager(spec=DEFAULT_MODEL)
        self.project: ProjectDatabase | None = None
        self.project_path: Path | None = None
        self.current_page = 1
        self.current_line_id: int | None = None
        self.current_line_text: str | None = None
        self.current_line_annotations: list[dict[str, object]] = []
        self.thresholds = ConfidenceThresholds()
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._processing_progress: QProgressDialog | None = None
        self._install_thread: QThread | None = None
        # The download keeps its own manager: self.model_manager follows the open project and
        # may change (transcription, model selection) while a download is still running.
        self._install_manager: ModelManager | None = None
        self._install_worker: ModelInstallWorker | None = None
        self._install_progress: QProgressDialog | None = None
        self._install_progress_timer: QTimer | None = None
        self._install_phase = "idle"
        self._model_manager_dialog: ModelManagerDialog | None = None
        self._tutorial_overlay: TutorialOverlay | None = None
        self._tutorial_targets: dict[str, QWidget] = {}
        self._last_resegmentation_backup: Path | None = None
        self._edit_timer = QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(700)
        self._edit_timer.timeout.connect(self.save_current_edit)
        self._display_scale_x = 1.0
        self._display_scale_y = 1.0
        self._hovered_line_id: int | None = None
        self.autosave_enabled = QSettings().value("editor/autosave", True, type=bool)
        self.show_reading_order = QSettings().value("view/reading_order", True, type=bool)
        self._tag_overview: TagOverviewDialog | None = None
        self._last_tag_label: str | None = None
        self.actions: dict[str, QAction] = {}
        self._overlays: list[QGraphicsPolygonItem] = []
        self._build_ui()
        self._build_actions()
        self._apply_style()
        self._show_welcome_status()
        if offer_model_on_startup:
            QTimer.singleShot(150, self._run_onboarding)

    def _build_ui(self) -> None:
        self.scene = QGraphicsScene(self)
        self.viewer = QGraphicsView(self.scene)
        self.viewer.setObjectName("documentViewer")
        self.viewer.setDragMode(QGraphicsView.ScrollHandDrag)
        # Smooth scaling keeps fine pen strokes legible when the page is zoomed out.
        self.viewer.setRenderHints(
            self.viewer.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.line_list = LineListWidget()
        self.line_list.setObjectName("lineList")
        self.line_list.currentItemChanged.connect(self._select_line)
        self.line_list.line_hovered.connect(self._hover_line)
        self.line_list.order_changed.connect(self._store_list_order)
        self.line_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.line_list.customContextMenuRequested.connect(self._line_list_menu)
        self.editor = TranscriptionEditor()
        self.editor.context_menu_extender = self._extend_editor_menu
        self.editor.setObjectName("transcriptionEditor")
        self.editor.setPlaceholderText("Select a line to review or correct its transcription.")
        self.editor.setEnabled(False)
        font = self.editor.font()
        font.setPointSize(QSettings().value("editor/font_size", 12, type=int))
        self.editor.setFont(font)
        self.editor.textChanged.connect(self._schedule_autosave)
        self.superscript_button = QPushButton("x²")
        self.superscript_button.setCheckable(True)
        self.superscript_button.setToolTip(
            f"Superscript ({shortcut_text(SHORTCUTS['superscript'][0])})"
        )
        self.superscript_button.clicked.connect(lambda: self._toggle_vertical_format("superscript"))
        self.subscript_button = QPushButton("x₂")
        self.subscript_button.setCheckable(True)
        self.subscript_button.setToolTip(f"Subscript ({shortcut_text(SHORTCUTS['subscript'][0])})")
        self.subscript_button.clicked.connect(lambda: self._toggle_vertical_format("subscript"))
        highlight = QPushButton("Highlight")
        highlight.setToolTip("Highlight the selected text")
        highlight.clicked.connect(self._highlight_selection)
        tag = QPushButton("Tag…")
        tag.setToolTip(
            "Tag the selected text or the word at the cursor as a person, place, date, … "
            f"({shortcut_text(SHORTCUTS['tag'][0])}; also on right-click)"
        )
        tag.clicked.connect(lambda: self._tag_selection())
        clear_format = QPushButton("Clear format")
        clear_format.setToolTip(
            "Remove highlighting, tags, superscript and subscript from the selection"
        )
        clear_format.clicked.connect(self._clear_selection_format)
        special = QToolButton()
        special.setText("Special character")
        special.setPopupMode(QToolButton.InstantPopup)
        special_menu = QMenu(special)
        for character in SPECIAL_CHARACTERS:
            special_menu.addAction(
                character,
                lambda _checked=False, value=character: self._insert_character(value),
            )
        special.setMenu(special_menu)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 28)
        self.font_size.setValue(self.editor.font().pointSize())
        self.font_size.setPrefix("Text ")
        self.font_size.setSuffix(" pt")
        self.font_size.setToolTip("Change the transcription editor text size")
        self.font_size.valueChanged.connect(self._set_editor_font_size)
        format_row = QHBoxLayout()
        for control in (
            self.superscript_button,
            self.subscript_button,
            highlight,
            tag,
            clear_format,
            special,
            self.font_size,
        ):
            format_row.addWidget(control)
        format_row.addStretch(1)
        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addLayout(format_row)
        editor_layout.addWidget(self.editor)
        # Names every tag of the edited line next to its words; click to select or remove.
        self.tag_panel = QLabel()
        self.tag_panel.setObjectName("tagPanel")
        self.tag_panel.setWordWrap(True)
        self.tag_panel.setTextFormat(Qt.RichText)
        self.tag_panel.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.tag_panel.linkActivated.connect(self._tag_panel_link)
        editor_layout.addWidget(self.tag_panel)
        self._editor_tags: list[TagSpan] = []
        self.editor.textChanged.connect(self._update_tag_panel)
        self.status_label = QLabel()
        self.status_label.setObjectName("contextStatus")
        self.status_label.setWordWrap(True)
        verify = QPushButton("Mark selected line as verified")
        verify.clicked.connect(self._verify_line)
        next_uncertain = QPushButton("Next uncertain line")
        next_uncertain.clicked.connect(self._next_uncertain)
        right = QWidget()
        right.setObjectName("reviewCard")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.status_label)
        self.review_splitter = QSplitter(Qt.Vertical)
        self.review_splitter.setObjectName("reviewSplitter")
        self.review_splitter.setChildrenCollapsible(False)
        self.review_splitter.addWidget(self.line_list)
        self.review_splitter.addWidget(editor_panel)
        self.review_splitter.setSizes([430, 250])
        right_layout.addWidget(self.review_splitter, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(verify)
        buttons.addWidget(next_uncertain)
        right_layout.addLayout(buttons)

        splitter = QSplitter()
        splitter.addWidget(self.viewer)
        splitter.addWidget(right)
        splitter.setSizes([760, 520])
        self.setCentralWidget(splitter)
        self._tutorial_targets["review"] = right
        self.statusBar().showMessage("Ready")

    def _apply_style(self) -> None:
        """A restrained Material-inspired palette adapted from OpenEarable's visual language."""

        self.setStyleSheet(
            """
            QMainWindow { background: #F4F7FB; color: #20252B; }
            QMenuBar { background: #FFFFFF; color: #20252B; padding: 4px 8px; border-bottom: 1px solid #E2E7ED; }
            QMenuBar::item { padding: 7px 10px; border-radius: 7px; }
            QMenuBar::item:selected { background: #F0E7E6; }
            QMenu { background: #FFFFFF; color: #20252B; border: 1px solid #DDE3EA; padding: 6px; }
            QMenu::item { padding: 7px 26px 7px 10px; border-radius: 6px; }
            QMenu::item:selected { background: #F0E7E6; color: #5E3F3C; }
            QMenu::item:disabled { color: #9AA2AB; }
            QToolBar { background: #FFFFFF; border: 0; border-bottom: 1px solid #E2E7ED; spacing: 6px; padding: 7px 10px; }
            QToolButton, QPushButton { background: #F0E7E6; color: #5E3F3C; border: 1px solid #DECBC9; border-radius: 10px; padding: 7px 12px; font-weight: 600; }
            QToolButton:hover, QPushButton:hover { background: #E7D7D5; }
            QToolButton:pressed, QPushButton:pressed { background: #D9C2BF; }
            QToolButton:disabled, QPushButton:disabled { background: #EEF0F3; color: #9AA2AB; border-color: #E1E5E9; }
            QGraphicsView, QListWidget, QTextEdit, QTextBrowser, QTableWidget, QLineEdit { background: #FFFFFF; color: #20252B; border: 1px solid #DDE3EA; border-radius: 12px; selection-background-color: #DCC8C5; selection-color: #20252B; }
            QGraphicsView { margin: 8px 4px 8px 8px; }
            QWidget#reviewCard { background: #FFFFFF; border: 1px solid #DDE3EA; border-radius: 18px; }
            QLabel#contextStatus { color: #56616D; padding: 8px 4px; }
            QLabel#tagPanel { color: #56616D; padding: 4px 2px; }
            QLabel#tutorialHeading { font-size: 24px; font-weight: 700; color: #5E3F3C; }
            QFrame#tutorialCard { background: #FFFFFF; border: 1px solid #D9DEE5; border-radius: 18px; }
            QLabel#tutorialKicker { color: #9A6F6B; font-size: 11px; font-weight: 800; }
            QLabel#tutorialBody { color: #4F5B66; font-size: 14px; }
            QScrollArea#tutorialBodyScroll { background: transparent; border: none; }
            QScrollArea#tutorialBodyScroll > QWidget > QWidget { background: transparent; }
            QLabel#tutorialProgress { color: #7A858F; font-weight: 600; }
            QSpinBox { background: #FFFFFF; color: #20252B; border: 1px solid #DDE3EA; border-radius: 9px; padding: 6px 24px 6px 8px; min-width: 112px; }
            QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 20px; background: #F0E7E6; border-left: 1px solid #DECBC9; }
            QSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 9px; }
            QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 9px; border-top: 1px solid #DECBC9; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #E7D7D5; }
            QProgressDialog { background: #F4F7FB; }
            QProgressDialog QLabel { color: #20252B; }
            QHeaderView::section { background: #F0E7E6; color: #5E3F3C; padding: 7px; border: 0; border-right: 1px solid #DECBC9; font-weight: 600; }
            QStatusBar { background: #FFFFFF; border-top: 1px solid #E2E7ED; color: #68737E; }
            """
            + self._spin_arrow_style()
        )

    @staticmethod
    def _spin_arrow_style() -> str:
        """Image arrows for styled spin boxes; Qt draws none once the buttons are styled."""

        assets = (Path(__file__).resolve().parent.parent / "assets").as_posix()
        rules = []
        for direction in ("up", "down"):
            arrow = f"QSpinBox::{direction}-arrow"
            rules.append(f'{arrow} {{ image: url("{assets}/spin-{direction}.png"); width: 10px; height: 6px; }}')
            rules.append(
                f'{arrow}:disabled, {arrow}:off {{ image: url("{assets}/spin-{direction}-disabled.png"); }}'
            )
        return "\n".join(rules)

    def _run_onboarding(self) -> None:
        settings = QSettings()
        if not settings.value("onboarding/tutorial_seen", False, type=bool):
            self._start_tutorial(first_run=True)
        elif not self.model_manager.status().installed:
            self._offer_model_installation()

    @Slot()
    def show_tutorial(self) -> None:
        self._start_tutorial(first_run=False)

    def _start_tutorial(self, *, first_run: bool) -> None:
        if self._tutorial_overlay:
            self._tutorial_overlay.show()
            self._tutorial_overlay.raise_()
            return
        steps = [
            (
                "Welcome to KurrentScholar",
                "KurrentScholar helps you turn scanned historical German handwriting into an "
                "editable, reviewable transcription on this computer. Open a manuscript, choose "
                "which pages to process, compare every detected line with the image, and export a "
                "research-ready result. Let’s take a quick tour of the workspace.",
                None,
            ),
            (
                "Start with a manuscript",
                "Open a PDF or archival image here. KurrentScholar creates a .ksproj research "
                "project beside your source so transcription, corrections, and review status can "
                "be reopened later.",
                self._tutorial_targets.get("open"),
            ),
            (
                "Navigate and choose the scope",
                "Use Previous, Next, or the page selector to move directly to any page. The "
                "Transcribe menu can process the current page, a page range, or the full document.",
                self._tutorial_targets.get("transcribe"),
            ),
            (
                "Review results while they arrive",
                "Recognized lines appear here during transcription. Select or hover over a line to "
                "highlight its box on the manuscript, correct the text, and mark it verified only "
                "after comparing it with the image. Drag a line up or down to change the reading "
                "order; the numbers on the page boxes and all exports follow it.",
                self._tutorial_targets.get("review"),
            ),
            (
                "Export your work",
                "Use the Export menu in the menu bar"
                f"{' at the top of the screen' if sys.platform == 'darwin' else ''}. "
                "Choose plain text, Word, CSV, "
                "Excel, or research JSON; verified line crops for external fine-tuning are available "
                "there as a separate ground-truth bundle.",
                self._tutorial_targets.get("export"),
            ),
            (
                "Correct and annotate",
                "Drag the divider below the line list to resize the editor. Its formatting controls "
                "support superscript, subscript, highlights, named tags, and historical special "
                "characters. Tag a word as a person, place, date, … with Tag… or by right-clicking "
                "it; the tag's name then appears beside the word, and Review > Tags in project "
                "lists every tag. You can replay this tour later from Help > Tutorial.",
                self._tutorial_targets.get("review"),
            ),
        ]
        overlay = TutorialOverlay(steps, self)
        self._tutorial_overlay = overlay

        def completed() -> None:
            self._tutorial_overlay = None
            if first_run:
                QSettings().setValue("onboarding/tutorial_seen", True)
                if not self.model_manager.status().installed:
                    QTimer.singleShot(100, self._offer_model_installation)

        overlay.finished.connect(completed)
        overlay.show()

    def _build_actions(self) -> None:
        def action(name, callback, shortcut=None, tip=""):
            created = QAction(name, self)
            created.triggered.connect(callback)
            if isinstance(shortcut, tuple):
                created.setShortcuts([QKeySequence(sequence) for sequence in shortcut])
            elif shortcut:
                created.setShortcut(shortcut)
            if tip:
                created.setStatusTip(tip)
            self.actions[name] = created
            return created

        open_document = action("Open document", self.open_document, QKeySequence.Open)
        open_project = action("Open project", self.open_project, "Ctrl+Shift+O")
        previous = action("Previous page", lambda: self._change_page(-1), "PgUp")
        next_page = action("Next page", lambda: self._change_page(1), "PgDown")
        go_to_page = action("Go to page…", self.go_to_page, "Ctrl+G")
        current = action("Transcribe current page", self.transcribe_current_page, "Ctrl+T")
        page_range = action("Transcribe page range…", self.transcribe_page_range, "Ctrl+Shift+T")
        all_pages = action("Transcribe full document", self.transcribe_all)
        resegment = action("Re-segment", self.resegment)
        select_model = action("Recognition model", self.select_recognition_model)
        manage_models = action("Model Manager", self.show_model_manager)
        save = action("Save", self.save_current_edit, QKeySequence.Save)
        autosave = action("Auto Save", self._set_autosave)
        autosave.setCheckable(True)
        autosave.setChecked(self.autosave_enabled)
        autosave.setStatusTip("Save shortly after typing; enabled by default")
        verify = action("Mark selected line verified", self._verify_line, "Ctrl+Shift+V")
        uncertain = action("Next uncertain line", self._next_uncertain, SHORTCUTS["next_uncertain"])
        evaluate = action("Evaluate corrections", self.evaluate_corrections)
        tag_overview = action(
            "Tags in project…", self.show_tag_overview,
            tip="List every tagged person, place, date, … and jump to it",
        )
        move_up = action(
            "Move line up", lambda: self._move_current_line(-1), SHORTCUTS["move_line_up"],
            tip="Read the selected line one place earlier",
        )
        move_down = action(
            "Move line down", lambda: self._move_current_line(1), SHORTCUTS["move_line_down"],
            tip="Read the selected line one place later",
        )
        restore_order = action(
            "Restore detected order", self._restore_detected_order,
            tip="Undo reading-order changes on this page",
        )
        show_order = action("Show reading order on page", self._set_show_reading_order)
        show_order.setCheckable(True)
        show_order.setChecked(self.show_reading_order)
        show_order.setStatusTip("Number each line box on the page in reading order")
        ground_truth = action("Export ground-truth bundle…", self.export_ground_truth_bundle)
        zoom_in = action("Zoom in", lambda: self.viewer.scale(1.2, 1.2), QKeySequence.ZoomIn)
        zoom_out = action("Zoom out", lambda: self.viewer.scale(1 / 1.2, 1 / 1.2), QKeySequence.ZoomOut)
        zoom_fit = action(
            "Fit page", lambda: self.viewer.fitInView(self.pixmap_item, Qt.KeepAspectRatio), "Ctrl+0"
        )
        tutorial = action("Tutorial", self.show_tutorial)
        diagnostic = action("Diagnostic log", self.show_diagnostic_log)
        about = action("About", self.about)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([open_document, open_project])
        file_menu.addSeparator()
        file_menu.addAction(action("Exit", self.close, QKeySequence.Quit))

        export_menu = self.menuBar().addMenu("&Export")
        for label, suffix in (
            ("Plain text…", ".txt"), ("Word document…", ".docx"),
            ("CSV table…", ".csv"), ("Excel workbook…", ".xlsx"),
            ("Research JSON…", ".json"),
        ):
            export_menu.addAction(action(f"Export {label}", lambda _checked=False, s=suffix: self.export_project(s)))
        export_menu.addSeparator()
        export_menu.addAction(ground_truth)
        self._tutorial_targets["export"] = self.menuBar()

        transcription_menu = self.menuBar().addMenu("&Transcription")
        transcription_menu.addActions([current, page_range, all_pages])
        transcription_menu.addSeparator()
        transcription_menu.addAction(resegment)

        review_menu = self.menuBar().addMenu("&Review")
        review_menu.addActions([save, autosave])
        review_menu.addSeparator()
        review_menu.addActions([verify, uncertain, evaluate])
        order_menu = review_menu.addMenu("Reading order")
        order_menu.addActions([move_up, move_down])
        order_menu.addSeparator()
        order_menu.addAction(restore_order)
        review_menu.addSeparator()
        review_menu.addAction(tag_overview)
        formatting_menu = review_menu.addMenu("Text formatting")
        formatting_menu.addAction(
            action("Tag selection…", self._tag_selection, SHORTCUTS["tag"])
        )
        formatting_menu.addAction(
            action(
                "Superscript",
                lambda: self._toggle_vertical_format("superscript"),
                SHORTCUTS["superscript"],
            )
        )
        formatting_menu.addAction(
            action(
                "Subscript",
                lambda: self._toggle_vertical_format("subscript"),
                SHORTCUTS["subscript"],
            )
        )
        formatting_menu.addAction(
            action("Clear text formatting", self._clear_selection_format, SHORTCUTS["clear_format"])
        )

        models_menu = self.menuBar().addMenu("&Models")
        models_menu.addActions([manage_models, select_model])

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions([previous, next_page, go_to_page])
        view_menu.addSeparator()
        view_menu.addActions([zoom_in, zoom_out, zoom_fit])
        view_menu.addSeparator()
        view_menu.addAction(show_order)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addActions([tutorial, diagnostic])
        help_menu.addSeparator()
        help_menu.addAction(about)

        toolbar = QToolBar("Primary actions")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        toolbar.addAction(open_document)
        toolbar.addAction(open_project)
        open_widget = toolbar.widgetForAction(open_document)
        if open_widget:
            self._tutorial_targets["open"] = open_widget
        toolbar.addSeparator()
        toolbar.addAction(previous)
        toolbar.addAction(next_page)
        self.page_selector = QSpinBox()
        self.page_selector.setObjectName("pageSelector")
        self.page_selector.setKeyboardTracking(False)
        self.page_selector.setPrefix("Page ")
        self.page_selector.setRange(1, 1)
        self.page_selector.setEnabled(False)
        self.page_selector.setToolTip(f"Go directly to a page ({shortcut_text('Ctrl+G')})")
        self.page_selector.valueChanged.connect(self._go_to_page)
        toolbar.addWidget(self.page_selector)
        toolbar.addSeparator()
        transcribe_button = QToolButton()
        transcribe_button.setText("Transcribe")
        transcribe_button.setToolTip("Choose which pages to transcribe")
        transcribe_button.setPopupMode(QToolButton.InstantPopup)
        transcribe_button.setMenu(transcription_menu)
        toolbar.addWidget(transcribe_button)
        self._tutorial_targets["transcribe"] = transcribe_button
        self._update_navigation_actions()

    def _update_navigation_actions(self) -> None:
        document = self.project.document() if self.project else None
        page_count = int(document["page_count"]) if document else 0
        self.actions["Previous page"].setEnabled(self.current_page > 1)
        self.actions["Next page"].setEnabled(0 < self.current_page < page_count)
        self.actions["Go to page…"].setEnabled(page_count > 0)
        if hasattr(self, "page_selector"):
            self.page_selector.blockSignals(True)
            self.page_selector.setRange(1, max(1, page_count))
            self.page_selector.setValue(min(max(1, self.current_page), max(1, page_count)))
            self.page_selector.setSuffix(f" of {page_count}" if page_count else "")
            self.page_selector.setEnabled(page_count > 0)
            self.page_selector.blockSignals(False)

    def _change_page(self, change: int) -> None:
        self._go_to_page(self.current_page + change)

    @Slot()
    def go_to_page(self) -> None:
        document = self.project.document() if self.project else None
        if not document:
            self._error("No project is open", "Open a manuscript first.")
            return
        target, accepted = QInputDialog.getInt(
            self,
            "Go to page",
            f"Page number (1-{document['page_count']}):",
            self.current_page,
            1,
            int(document["page_count"]),
        )
        if accepted:
            self._go_to_page(target)

    @Slot(int)
    def _go_to_page(self, target: int) -> None:
        document = self.project.document() if self.project else None
        if not document or not 1 <= target <= int(document["page_count"]):
            self._update_navigation_actions()
            return
        if target == self.current_page:
            self._update_navigation_actions()
            return
        self.save_current_edit()
        self.current_page = target
        self._render_page()
        self._refresh_lines()
        self.status_label.setText(f"Page {self.current_page} of {document['page_count']}.")

    @Slot(bool)
    def _set_autosave(self, enabled: bool) -> None:
        self.autosave_enabled = bool(enabled)
        QSettings().setValue("editor/autosave", self.autosave_enabled)
        if self.autosave_enabled:
            self._schedule_autosave()
            self.statusBar().showMessage("Auto Save is on.", 4_000)
        else:
            self._edit_timer.stop()
            self.statusBar().showMessage(
                f"Auto Save is off. Use {shortcut_text(QKeySequence.Save)}; edits are still protected "
                "when changing context or closing.",
                7_000,
            )

    def _show_welcome_status(self) -> None:
        status = self.model_manager.status()
        if status.installed:
            text = "Handwriting model installed. Open a PDF or archival image to begin."
        else:
            text = ("Welcome. The separate 1.34 GB handwriting model is not installed. Install it once "
                    "while online from Models > Model Manager; documents are never uploaded and later "
                    "transcription is offline.")
        self.status_label.setText(text)

    def _offer_model_installation(self) -> None:
        if self.model_manager.status().installed or self._install_running():
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Information)
        dialog.setWindowTitle("Handwriting model required")
        dialog.setText("Install the handwriting model now?")
        dialog.setInformativeText(
            "KurrentScholar cannot transcribe documents until this separate model is installed. "
            "The one-time download is about 1.34 GB and requires an internet connection. "
            "Your documents are not uploaded, and transcription works offline afterward."
        )
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.button(QMessageBox.Yes).setText("Install model")
        dialog.button(QMessageBox.No).setText("Not now")
        if dialog.exec() == QMessageBox.Yes:
            self._start_model_installation()

    def dragEnterEvent(self, event) -> None:
        if (not self._thread or not self._thread.isRunning()) and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if self._thread and self._thread.isRunning():
            self.statusBar().showMessage(
                "Finish or cancel transcription before opening another document.", 7_000
            )
            event.ignore()
            return
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        if paths:
            if paths[0].suffix.lower() == ".ksproj":
                self._load_project(paths[0])
            else:
                self._create_project_for_document(paths[0])

    @Slot()
    def open_document(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open manuscript", "", "Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff)"
        )
        if filename:
            self._create_project_for_document(Path(filename))

    def _create_project_for_document(self, source: Path) -> None:
        try:
            page_count = self.renderer.page_count(source)
        except Exception as error:
            self._error("The document could not be opened", str(error))
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Create research project", str(source.with_suffix(".ksproj")), "KurrentScholar (*.ksproj)"
        )
        if not destination:
            return
        try:
            project_path = Path(destination)
            if project_path.exists():
                answer = QMessageBox.question(
                    self,
                    "Replace existing project?",
                    f"{project_path.name} already exists. Replacing it permanently deletes that "
                    "project's stored transcriptions and corrections. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
                if self.project and self.project_path and (
                    self.project_path.resolve() == project_path.resolve()
                ):
                    self.save_current_edit()
                    self.project.close()
                    self.project = None
            new_project = ProjectDatabase(project_path, create=True, overwrite=True)
            new_project.set_document(source, page_count)
            if self.project:
                self.project.close()
            self.project_path = project_path
            self.project = new_project
            if self._tag_overview:  # its entries belong to the previous project
                self._tag_overview.close()
            self.current_page = 1
            self._render_page()
            self._refresh_lines()
            self.status_label.setText(
                f"Project created. Page 1 of {page_count}. Choose Transcribe when ready."
            )
        except Exception as error:
            self._error("The project could not be created", str(error), exception_details(error))

    @Slot()
    def open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open project", "", "KurrentScholar (*.ksproj)")
        if filename:
            self._load_project(Path(filename))

    def _load_project(self, path: Path) -> None:
        new_project: ProjectDatabase | None = None
        try:
            new_project = ProjectDatabase(path)
            document = new_project.document()
            if not document:
                raise FileNotFoundError("The project has no source document record.")
            if not Path(document["source_path"]).is_file():
                replacement, _ = QFileDialog.getOpenFileName(
                    self,
                    "Relink the moved source document",
                    "",
                    "Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff)",
                )
                if not replacement:
                    raise FileNotFoundError(
                        "The original document is missing. Reopen the project and select the moved original file."
                    )
                new_project.relink_document(replacement)
            if self.project:
                self.project.close()
            self.project = new_project
            if self._tag_overview:  # its entries belong to the previous project
                self._tag_overview.close()
            new_project = None
            self.project_path = path
            self.current_page = 1
            self._render_page()
            self._refresh_lines()
            self.status_label.setText(f"Opened {path.name}")
        except Exception as error:
            if new_project:
                new_project.close()
            self._error("The project could not be opened", str(error))

    def _render_page(self) -> None:
        if not self.project:
            return
        document = self.project.document()
        if not document:
            return
        try:
            rendered = self.renderer.render(document["source_path"], self.current_page - 1, dpi=150)
        except Exception as error:
            # E.g. the source sits on a disconnected drive. Keep the project usable instead of
            # leaving navigation or project opening half-finished.
            LOGGER.error("Page %s could not be displayed\n%s", self.current_page, exception_details(error))
            self.pixmap_item.setPixmap(QPixmap())
            self._sync_display_scale_from_project_page()
            message = f"Page {self.current_page} could not be displayed: {error}"
            self.status_label.setText(message)
            self.statusBar().showMessage(message, 15_000)
            self._update_navigation_actions()
            return
        qt_image = ImageQt(rendered.image)
        self.pixmap_item.setPixmap(QPixmap.fromImage(qt_image))
        self._sync_display_scale_from_project_page()
        self.scene.setSceneRect(QRectF(self.pixmap_item.boundingRect()))
        self.viewer.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        self._update_navigation_actions()

    def _sync_display_scale_from_project_page(self) -> None:
        """Map stored detection coordinates to the currently displayed page image."""

        page = self.project.page(self.current_page) if self.project else None
        pixmap = self.pixmap_item.pixmap()
        if page and not pixmap.isNull() and page["width"] > 0 and page["height"] > 0:
            self._display_scale_x = pixmap.width() / page["width"]
            self._display_scale_y = pixmap.height() / page["height"]
        else:
            self._display_scale_x = self._display_scale_y = 1.0

    def _refresh_lines(self, preserve_selection: bool = True) -> None:
        selected_id = self.current_line_id if preserve_selection else None
        if preserve_selection:
            self.save_current_edit()
        # Live transcription refreshes the list after every saved line; keep the
        # reviewer's caret and scroll position so ongoing corrections are not disrupted.
        editor_cursor = self.editor.textCursor()
        cursor_anchor, cursor_position = editor_cursor.anchor(), editor_cursor.position()
        list_scroll = self.line_list.verticalScrollBar().value()
        self.line_list.blockSignals(True)
        self._edit_timer.stop()
        self.current_line_id = None
        self.current_line_text = None
        self.current_line_annotations = []
        self._hovered_line_id = None
        self.line_list.clear()
        for overlay in self._overlays:
            self.scene.removeItem(overlay)
        self._overlays.clear()
        selected_row = -1
        if self.project:
            for line in self.project.lines(self.current_page):
                item = QListWidgetItem()
                item.setData(Qt.UserRole, line.id)
                self._describe_line_item(item, line)
                self.line_list.addItem(item)
                if line.id == selected_id:
                    selected_row = self.line_list.count() - 1
                box = line.bbox
                points = line.polygon or [
                    (box.x, box.y),
                    (box.right, box.y),
                    (box.right, box.bottom),
                    (box.x, box.bottom),
                ]
                polygon = QPolygonF(
                    [
                        QPointF(x * self._display_scale_x, y * self._display_scale_y)
                        for x, y in points
                    ]
                )
                overlay = QGraphicsPolygonItem(polygon)
                overlay.setPen(QPen(QColor("#9A6F6B"), 2))
                overlay.setData(0, line.id)
                if self.show_reading_order:
                    self._add_order_badge(overlay, line.position + 1)
                self.scene.addItem(overlay)
                self._overlays.append(overlay)
        self.line_list.blockSignals(False)
        self.line_list.verticalScrollBar().setValue(list_scroll)
        if selected_row >= 0:
            self.line_list.setCurrentRow(selected_row)
            length = len(self.editor.toPlainText())
            restored = self.editor.textCursor()
            restored.setPosition(min(cursor_anchor, length))
            restored.setPosition(min(cursor_position, length), QTextCursor.KeepAnchor)
            self.editor.setTextCursor(restored)
        else:
            self.editor.blockSignals(True)
            self.editor.clear()
            self.editor.blockSignals(False)
            self.editor.setEnabled(False)
            self._update_tag_panel()
            self._update_overlay_highlights()

    def _add_order_badge(self, overlay: QGraphicsPolygonItem, number: int) -> None:
        """Label a line box with its place in the reading order, just left of its corner."""

        bounds = overlay.polygon().boundingRect()
        text = QGraphicsSimpleTextItem(str(number))
        font = QFont(self.font())
        font.setPixelSize(max(12, min(26, round(bounds.height() * 0.45))))
        font.setBold(True)
        text.setFont(font)
        text.setBrush(QBrush(QColor("#FFFFFF")))
        label = text.boundingRect()
        badge = QGraphicsRectItem(0, 0, label.width() + 8, label.height() + 2, overlay)
        badge.setBrush(QBrush(QColor(154, 111, 107, 215)))
        badge.setPen(QPen(Qt.NoPen))
        badge.setPos(max(0.0, bounds.left() - badge.rect().width() - 2), bounds.top())
        text.setParentItem(badge)
        text.setPos(4, 1)

    @Slot(bool)
    def _set_show_reading_order(self, enabled: bool) -> None:
        self.show_reading_order = bool(enabled)
        QSettings().setValue("view/reading_order", self.show_reading_order)
        self._refresh_lines()

    def _project_model_spec(self) -> ModelSpec:
        if not self.project:
            return DEFAULT_MODEL
        info = self.project.info()
        model_id = info.get("model_id")
        revision = info.get("model_revision")
        if not model_id and not revision:
            return DEFAULT_MODEL
        spec = find_model(model_id or "", revision or "")
        if spec is None:
            raise ValueError(
                "This project uses an unknown recognition model "
                f"({model_id or 'missing id'} at {revision or 'missing revision'}). "
                "Its existing results remain readable, but KurrentScholar will not mix them "
                "with output from a different model."
            )
        return spec

    @Slot()
    def select_recognition_model(self) -> None:
        if not self.project:
            self._error("No project is open", "Open or create a project first.")
            return
        try:
            current = self._project_model_spec()
        except ValueError as error:
            self._error("The project model is unavailable", str(error))
            return
        labels = [spec.display_name for spec in MODEL_CATALOG]
        selected_label, accepted = QInputDialog.getItem(
            self,
            "Recognition model",
            "Choose the model for future transcription in this project.\n"
            "Changing a processed project requires a backed-up clean retranscription.",
            labels,
            labels.index(current.display_name),
            False,
        )
        if not accepted:
            return
        selected = next(spec for spec in MODEL_CATALOG if spec.display_name == selected_label)
        if selected == current:
            self.status_label.setText(f"Recognition model: {current.display_name}")
            return
        self._change_recognition_model(current, selected)

    def _change_recognition_model(self, current: ModelSpec, selected: ModelSpec) -> None:
        """Assign an installed model to the open project, backing up results it replaces."""

        if not self.project:
            return
        manager = ModelManager(spec=selected)
        if not manager.status().installed:
            self._error(
                "The selected model is not installed",
                f"Install ‘{selected.display_name}’ in Models > Model Manager, then select it again. "
                "No project data was changed.",
            )
            return
        summary = self.project.transcription_summary()
        if summary["line_count"] and not self._backup_and_reset_transcription(
            f"Changing from ‘{current.display_name}’ to ‘{selected.display_name}’ requires "
            "replacing the current machine transcription.",
            operation="change recognition model",
            backup_suffix="before-model-change",
        ):
            return
        self.project.set_info({
            "model_id": selected.model_id,
            "model_revision": selected.revision,
        })
        self.model_manager = manager
        self.status_label.setText(
            f"Recognition model changed to {selected.display_name}. Choose Transcribe to process the document."
        )
        if self._model_manager_dialog:
            self._model_manager_dialog.project_model = selected
            self._model_manager_dialog.refresh()

    @Slot()
    def transcribe_current_page(self) -> None:
        self._prepare_transcription([self.current_page - 1])

    @Slot()
    def transcribe_page_range(self) -> None:
        document = self.project.document() if self.project else None
        if not document:
            self._error("No project is open", "Open a manuscript first.")
            return
        specification, accepted = QInputDialog.getText(
            self,
            "Transcribe page range",
            f"Pages to transcribe (1-{document['page_count']}):",
            text=str(self.current_page),
        )
        if not accepted:
            return
        try:
            pages = parse_page_range(specification, int(document["page_count"]))
        except PageRangeError as error:
            self._error("Invalid page range", str(error))
            return
        self._prepare_transcription(pages)

    @Slot()
    def transcribe_all(self) -> None:
        document = self.project.document() if self.project else None
        pages = list(range(int(document["page_count"]))) if document else []
        self._prepare_transcription(pages)

    def _prepare_transcription(self, pages: list[int]) -> None:
        if not self.project or not self.project_path:
            self._error("No project is open", "Open a manuscript first.")
            return
        if self._thread and self._thread.isRunning():
            self.statusBar().showMessage("Transcription is already running.", 5_000)
            return
        if not pages:
            self._error("No pages selected", "Choose at least one page to transcribe.")
            return
        try:
            model_spec = self._project_model_spec()
        except ValueError as error:
            self._error("The project model is unavailable", str(error))
            return
        self.model_manager = ModelManager(spec=model_spec)
        status = self.model_manager.status()
        if not status.installed:
            self._error(
                "The project’s handwriting model is not installed",
                f"Install ‘{model_spec.display_name}’ and retry. Existing project results were not changed.",
            )
            return
        document = self.project.document()
        if not document:
            self._error("The project is incomplete", "No source document is recorded.")
            return
        segmenter = ProjectionSegmenter()
        summary = self.project.transcription_summary()
        info = self.project.info()
        if summary["line_count"] and (
            info.get("segmentation_backend") != segmenter.backend_id
            or info.get("segmentation_version") != segmenter.version
        ):
            if not self._backup_and_reset_transcription(
                "This project was processed with an older line detector. Its boxes and text "
                "cannot safely be matched to the new line-level boxes."
            ):
                return
        self._start_transcription(document, status.path, model_spec, pages)

    @Slot()
    def resegment(self) -> None:
        if not self.project or not self.project_path:
            self._error("No project is open", "Open a manuscript first.")
            return
        summary = self.project.transcription_summary()
        if summary["line_count"] and not self._backup_and_reset_transcription(
            "Re-segmentation replaces all current boxes and transcriptions."
        ):
            return
        self.transcribe_all()

    def _backup_and_reset_transcription(
        self,
        reason: str,
        operation: str = "re-segment",
        backup_suffix: str = "before-resegment",
    ) -> bool:
        if not self.project or not self.project_path:
            return False
        summary = self.project.transcription_summary()
        protected = summary["corrected_count"] + summary["reviewed_count"]
        protected_message = (
            f" This includes {summary['corrected_count']} corrected and "
            f"{summary['reviewed_count']} reviewed line(s)."
            if protected
            else ""
        )
        answer = QMessageBox.question(
            self,
            f"Back up and {operation}?",
            f"{reason}\n\nThe current {summary['line_count']} line result(s) will be saved "
            f"in a separate backup project before replacement.{protected_message}\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return False

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = self.project_path.with_name(
            f"{self.project_path.stem}.{backup_suffix}-{stamp}.ksproj"
        )
        backup_path = base
        counter = 2
        while backup_path.exists():
            backup_path = base.with_name(f"{base.stem}-{counter}{base.suffix}")
            counter += 1
        try:
            self.project.backup_to(backup_path)
            self.project.reset_transcription()
            self._last_resegmentation_backup = backup_path
            LOGGER.info("Backed up project to %s before re-segmentation", backup_path)
            self._refresh_lines()
            return True
        except Exception as error:
            details = exception_details(error)
            LOGGER.error("Could not prepare safe re-segmentation\n%s", details)
            self._error(
                "Re-segmentation could not start",
                "The existing results were not replaced because the backup could not be created.",
                details,
            )
            return False

    def _start_transcription(
        self,
        document: dict,
        model_path: Path,
        model_spec: ModelSpec,
        pages: list[int],
    ) -> None:
        self._thread = QThread(self)
        self._worker = ProcessingWorker(self.project_path, pages, model_path, model_spec)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._processing_progress = QProgressDialog(
            "Preparing transcription…", "Cancel", 0, len(pages), self
        )
        self._processing_progress.setWindowModality(Qt.NonModal)
        self._processing_progress.setAutoClose(False)
        self._processing_progress.canceled.connect(self._request_processing_cancel)
        self._worker.progress.connect(self._update_processing_progress)
        self._worker.line_saved.connect(self._processing_line_saved)
        self._worker.finished.connect(self._processing_done)
        self._worker.failed.connect(self._processing_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._processing_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._set_processing_busy(True)
        LOGGER.info("Starting transcription thread")
        self.statusBar().showMessage(
            f"Transcribing {len(pages)} selected page(s); completed lines appear live."
        )
        self._thread.start()

    @Slot(int, int)
    def _processing_line_saved(self, page_number: int, _line_id: int) -> None:
        if page_number == self.current_page and self.project:
            # The worker detects at 300 DPI while the viewer uses 150 DPI. Page
            # geometry is available before the first line signal, so synchronize
            # the transform immediately instead of waiting for the final refresh.
            self._sync_display_scale_from_project_page()
            self._refresh_lines(preserve_selection=True)
        self.statusBar().showMessage(f"Saved a line on page {page_number}; transcription continues.")

    @Slot()
    def _request_processing_cancel(self) -> None:
        if self._worker:
            self._worker.request_cancel()
        if self._processing_progress:
            self._processing_progress.setLabelText("Stopping safely after the current line…")
            self._processing_progress.setCancelButton(None)
            self._processing_progress.show()
        LOGGER.info("Transcription cancellation requested")

    @Slot(int, int, str)
    def _update_processing_progress(self, value: int, maximum: int, text: str) -> None:
        if not self._processing_progress:
            return
        self._processing_progress.setMaximum(maximum)
        self._processing_progress.setValue(value)
        self._processing_progress.setLabelText(text)

    @Slot(bool)
    def _processing_done(self, cancelled: bool) -> None:
        LOGGER.info("Processing completion received on GUI thread: cancelled=%s", cancelled)
        if self._processing_progress:
            self._processing_progress.close()
            self._processing_progress = None
        self._set_processing_busy(False)
        if self.project:
            self._render_page()
            self._refresh_lines(preserve_selection=True)
        backup = self._last_resegmentation_backup
        self._last_resegmentation_backup = None
        if cancelled:
            message = "Transcription cancelled safely; completed lines were saved."
            if backup:
                message += f" Previous results: {backup}"
            self.status_label.setText(message)
        else:
            if backup:
                self.status_label.setText(
                    f"Re-segmentation and transcription completed. Previous results: {backup}"
                )
            else:
                self.status_label.setText("Transcription completed; all results were saved.")

    @Slot(str, str)
    def _processing_failed(self, message: str, details: str) -> None:
        if self._processing_progress:
            self._processing_progress.close()
            self._processing_progress = None
        self._set_processing_busy(False)
        LOGGER.error("Transcription failed: %s\n%s", message, details)
        if self.project:
            self._render_page()
            self._refresh_lines(preserve_selection=True)
        backup = self._last_resegmentation_backup
        self._last_resegmentation_backup = None
        if backup:
            message += f" The previous results remain available in {backup}."
        self._error("Transcription could not continue", message, details)

    @Slot()
    def _processing_thread_finished(self) -> None:
        LOGGER.info("Transcription thread stopped")
        self._worker = None
        self._thread = None

    def _set_processing_busy(self, busy: bool) -> None:
        for name in (
            "Open document",
            "Open project",
            "Transcribe full document",
            "Transcribe current page",
            "Transcribe page range…",
            "Re-segment",
            "Recognition model",
            "Model Manager",
        ):
            self.actions[name].setEnabled(not busy)

    @Slot()
    def show_model_manager(self) -> None:
        if self._model_manager_dialog:
            self._model_manager_dialog.refresh()
            self._model_manager_dialog.show()
            self._model_manager_dialog.raise_()
            return
        try:
            project_model = self._project_model_spec() if self.project else None
        except ValueError:
            project_model = None
        dialog = ModelManagerDialog(project_model, self)
        dialog.install_requested.connect(self._install_selected_model)
        dialog.remove_requested.connect(self._remove_selected_model)
        dialog.select_requested.connect(self._select_model_from_manager)
        dialog.finished.connect(lambda _result: setattr(self, "_model_manager_dialog", None))
        self._model_manager_dialog = dialog
        dialog.show()

    @Slot(object)
    def _install_selected_model(self, spec: ModelSpec) -> None:
        if self._thread and self._thread.isRunning():
            self._error("Transcription is active", "Wait for transcription to finish before installing a model.")
            return
        if self._install_running():
            self._error(
                "A model download is active",
                "Wait for the current model download to finish before installing another model.",
            )
            return
        self.model_manager = ModelManager(spec=spec)
        if self.model_manager.status().installed:
            QMessageBox.information(
                self,
                "Model installed",
                f"‘{spec.display_name}’ is already installed and verified.",
            )
            return
        size_gib = spec.required_bytes / (1024 ** 3)
        answer = QMessageBox.question(
            self,
            "Install model",
            f"Download {size_gib:.2f} GiB for ‘{spec.display_name}’ now? "
            "This contacts Hugging Face only for the model; no documents or transcriptions are sent. "
            "The pinned model is separate from KurrentScholar and works offline afterward.",
        )
        if answer != QMessageBox.Yes:
            return
        self._start_model_installation()

    @Slot(object)
    def _remove_selected_model(self, spec: ModelSpec) -> None:
        if self._thread and self._thread.isRunning():
            self._error("Transcription is active", "Wait for transcription to finish before removing a model.")
            return
        if self._install_running():
            self._error(
                "A model download is active",
                "Wait for the current model download to finish before removing a model.",
            )
            return
        manager = ModelManager(spec=spec)
        if not manager.downloaded_bytes():
            return
        active = False
        try:
            active = bool(self.project and self._project_model_spec() == spec)
        except ValueError:
            pass
        warning = (
            " This is the model selected by the open project. Existing results remain readable, "
            "but transcription cannot resume until it is reinstalled."
            if active else ""
        )
        answer = QMessageBox.question(
            self,
            "Remove downloaded model?",
            f"Remove ‘{spec.display_name}’ and free about "
            f"{manager.downloaded_bytes() / (1024 ** 3):.2f} GiB?{warning}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            manager.remove()
        except Exception as error:
            self._error("The model could not be removed", str(error), exception_details(error))
            return
        if self._model_manager_dialog:
            self._model_manager_dialog.refresh()
        self.statusBar().showMessage(f"Removed {spec.display_name}.", 7_000)

    @Slot(object)
    def _select_model_from_manager(self, selected: ModelSpec) -> None:
        if self._thread and self._thread.isRunning():
            self._error(
                "Transcription is active",
                "Wait for transcription to finish before changing the project's recognition model.",
            )
            return
        if not self.project:
            self._error("No project is open", "Open or create a project first.")
            return
        try:
            current = self._project_model_spec()
        except ValueError as error:
            self._error("The project model is unavailable", str(error))
            return
        if selected == current:
            return
        self._change_recognition_model(current, selected)

    def _install_running(self) -> bool:
        return bool(self._install_thread and self._install_thread.isRunning())

    def _start_model_installation(self) -> None:
        if self._install_running():
            if self._install_progress:
                self._install_progress.show()
                self._install_progress.raise_()
            return
        manager = self._install_manager = self.model_manager
        self.actions["Model Manager"].setEnabled(False)
        progress = QProgressDialog("Starting model download…", "Hide", 0, 1000, self)
        progress.setWindowTitle(f"Installing {manager.spec.display_name}")
        progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False)
        progress.setValue(0)
        progress.canceled.connect(progress.hide)
        progress.show()
        self._install_progress = progress
        self._install_phase = "download"
        self._install_progress_timer = QTimer(self)
        self._install_progress_timer.setInterval(500)
        self._install_progress_timer.timeout.connect(self._update_model_download_progress)
        self._install_progress_timer.start()
        self._install_thread = QThread(self)
        self._install_worker = ModelInstallWorker(manager)
        self._install_worker.moveToThread(self._install_thread)
        self._install_thread.started.connect(self._install_worker.run)
        self._install_worker.status.connect(self._model_install_status)
        self._install_worker.finished.connect(self._model_install_done)
        self._install_worker.failed.connect(self._model_install_failed)
        self._install_worker.finished.connect(self._install_thread.quit)
        self._install_worker.failed.connect(self._install_thread.quit)
        self._install_worker.finished.connect(self._install_worker.deleteLater)
        self._install_worker.failed.connect(self._install_worker.deleteLater)
        self._install_thread.finished.connect(self._model_install_thread_finished)
        self._install_thread.finished.connect(self._install_thread.deleteLater)
        LOGGER.info("Starting model installation thread")
        self._install_thread.start()

    @Slot(str)
    def _model_install_status(self, message: str) -> None:
        LOGGER.info("Model installation status: %s", message)
        lowered = message.lower()
        if lowered.startswith("downloading"):
            self._install_phase = "download"
        elif lowered.startswith("verifying"):
            self._install_phase = "verify"
        else:
            self._install_phase = "status"
        if self._install_progress:
            self._install_progress.setLabelText(message)

    @Slot()
    def _model_install_done(self) -> None:
        LOGGER.info("Model installation completion received on GUI thread")
        self._stop_install_progress_timer()
        manager = self._install_manager or self.model_manager
        status = manager.status()
        if not status.installed:
            self._model_install_failed(
                "The model worker finished, but the verified installation marker is missing.",
                f"Missing files: {', '.join(status.missing_files) or 'none'}\n"
                f"Invalid files: {', '.join(status.invalid_files) or 'none'}",
            )
            return
        if self._install_progress:
            self._install_progress.setValue(self._install_progress.maximum())
            self._install_progress.close()
        self._install_progress = None
        self._install_phase = "idle"
        self.actions["Model Manager"].setEnabled(True)
        if self._model_manager_dialog:
            self._model_manager_dialog.refresh()
        self.status_label.setText(f"{manager.spec.display_name} installed and ready offline.")
        QMessageBox.information(
            self,
            "Model installation complete",
            f"‘{manager.spec.display_name}’ was downloaded, verified, and is ready. "
            "It can now run without an internet connection.",
        )

    @Slot(str, str)
    def _model_install_failed(self, message: str, details: str) -> None:
        self._stop_install_progress_timer()
        if self._install_progress:
            self._install_progress.close()
        self._install_progress = None
        self._install_phase = "idle"
        self.actions["Model Manager"].setEnabled(True)
        if self._model_manager_dialog:
            self._model_manager_dialog.refresh()
        LOGGER.error("Model installation failed: %s\n%s", message, details)
        self._error(
            "The model installation did not finish",
            f"No project data was affected. {message}\n\nYou can retry from Models > Model Manager.",
            f"Diagnostic log: {log_path()}\n\n{details}",
        )

    def _stop_install_progress_timer(self) -> None:
        if self._install_progress_timer:
            self._install_progress_timer.stop()
            self._install_progress_timer.deleteLater()
            self._install_progress_timer = None

    @Slot()
    def _model_install_thread_finished(self) -> None:
        LOGGER.info("Model installation thread stopped")
        self._install_worker = None
        self._install_thread = None
        self._install_manager = None

    @Slot()
    def _update_model_download_progress(self) -> None:
        manager = self._install_manager
        if not manager or not self._install_progress or self._install_phase != "download":
            return
        downloaded = manager.downloaded_bytes()
        required = manager.spec.required_bytes
        value = min(999, int(downloaded * 1000 / required))
        self._install_progress.setValue(value)
        gib = downloaded / (1024 ** 3)
        total_gib = required / (1024 ** 3)
        self._install_progress.setLabelText(
            f"Downloading the handwriting model: {gib:.2f} of {total_gib:.2f} GiB. "
            "Completed data is reused after interruptions."
        )

    def _format_cursor(self, select_word: bool = False) -> QTextCursor | None:
        if not self.editor.isEnabled():
            return None
        cursor = self.editor.textCursor()
        if select_word and not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        return cursor

    def _toggle_vertical_format(self, kind: str) -> None:
        cursor = self._format_cursor()
        if cursor is None:
            return
        target = (
            QTextCharFormat.VerticalAlignment.AlignSuperScript
            if kind == "superscript"
            else QTextCharFormat.VerticalAlignment.AlignSubScript
        )
        current = cursor.charFormat().verticalAlignment()
        alignment = (
            QTextCharFormat.VerticalAlignment.AlignNormal if current == target else target
        )
        formatting = QTextCharFormat()
        formatting.setVerticalAlignment(alignment)
        if cursor.hasSelection():
            cursor.mergeCharFormat(formatting)
        else:
            self.editor.mergeCurrentCharFormat(formatting)
        self.superscript_button.setChecked(
            alignment == QTextCharFormat.VerticalAlignment.AlignSuperScript
        )
        self.subscript_button.setChecked(
            alignment == QTextCharFormat.VerticalAlignment.AlignSubScript
        )
        self._schedule_autosave()

    def _highlight_selection(self) -> None:
        cursor = self._format_cursor(select_word=True)
        if cursor is None or not cursor.hasSelection():
            self.statusBar().showMessage("Select text, or place the cursor inside a word, first.", 4_000)
            return

        def highlighted(formatting: QTextCharFormat) -> QTextCharFormat:
            formatting.setProperty(HIGHLIGHT_PROPERTY, HIGHLIGHT_COLOR)
            if not formatting.hasProperty(TAG_PROPERTY):  # a tag's color stays visible
                formatting.setBackground(QColor(HIGHLIGHT_COLOR))
            return formatting

        self._rewrite_formats(cursor.selectionStart(), cursor.selectionEnd(), highlighted)

    def _project_tag_colors(self) -> dict[str, str]:
        """Labels already used in this project, with the color they were given."""

        colors: dict[str, str] = {}
        if self.project:
            for line in self.project.tagged_lines():
                for span in tag_spans(line.display_text, line.annotations):
                    colors.setdefault(span.label, span.color)
        for span in self._editor_tags:
            colors.setdefault(span.label, span.color)
        return colors

    def _tag_choices(self) -> list[str]:
        custom = sorted(set(self._project_tag_colors()) - set(TAG_COLORS), key=str.casefold)
        return [*TAG_COLORS, *custom]

    def _choose_tag_label(self, selected_text: str) -> str | None:
        """Ask for a tag name; predefined and previously used names are offered."""

        choices = self._tag_choices()
        words = " ".join(selected_text.split())
        if len(words) > 40:
            words = words[:39] + "…"
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Tag selected text")
        dialog.setLabelText(f"Tag “{words}” as:\nChoose a tag, or type a new name.")
        dialog.setComboBoxItems(choices)
        dialog.setComboBoxEditable(True)
        dialog.setTextValue(self._last_tag_label if self._last_tag_label in choices else choices[0])
        if not dialog.exec():
            return None
        label = " ".join(dialog.textValue().split())[:60]
        return label or None

    @Slot()
    def _tag_selection(self) -> None:
        cursor = self._format_cursor(select_word=True)
        if cursor is None or not cursor.hasSelection():
            self.statusBar().showMessage("Select text, or place the cursor inside a word, first.", 4_000)
            return
        label = self._choose_tag_label(cursor.selectedText())
        if label:
            self._apply_tag(label)

    def _apply_tag(self, label: str) -> None:
        cursor = self._format_cursor(select_word=True)
        if cursor is None or not cursor.hasSelection():
            self.statusBar().showMessage("Select text, or place the cursor inside a word, first.", 4_000)
            return
        known = self._project_tag_colors().get(label)
        color = TAG_COLORS.get(label) or known or custom_tag_color(label)
        tagged = tag_format(label, color)

        def retagged(formatting: QTextCharFormat) -> QTextCharFormat:
            formatting.merge(tagged)
            return formatting

        self._rewrite_formats(cursor.selectionStart(), cursor.selectionEnd(), retagged)
        self._last_tag_label = label
        # Continue typing after the tagged words without extending the tag.
        cursor.setPosition(cursor.selectionEnd())
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self._schedule_autosave()
        self.statusBar().showMessage(f"Tagged as {label}.", 3_000)

    def _rewrite_formats(self, start: int, end: int, transform) -> None:
        """Replace the format of every formatted piece of a range with transform(copy).

        Merging a format can add properties but never remove them, so removals (and
        changes that depend on a piece's existing tag) rewrite each piece explicitly.
        """

        document = self.editor.document()
        pieces: list[tuple[int, int, QTextCharFormat]] = []
        block = document.findBlock(start)
        while block.isValid() and block.position() < end:
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                iterator += 1
                if not fragment.isValid():
                    continue
                low = max(start, fragment.position())
                high = min(end, fragment.position() + fragment.length())
                if low < high:
                    pieces.append((low, high, QTextCharFormat(fragment.charFormat())))
            block = block.next()
        for low, high, formatting in pieces:
            cursor = QTextCursor(document)
            cursor.setPosition(low)
            cursor.setPosition(high, QTextCursor.KeepAnchor)
            cursor.setCharFormat(transform(formatting))
        self._schedule_autosave()

    def _strip_formats(
        self, start: int, end: int, *, tags: bool, highlights: bool, vertical: bool
    ) -> None:
        def stripped(formatting: QTextCharFormat) -> QTextCharFormat:
            if tags:
                formatting = untagged_format(formatting)
            if highlights and formatting.hasProperty(HIGHLIGHT_PROPERTY):
                formatting.clearProperty(HIGHLIGHT_PROPERTY)
                if not formatting.hasProperty(TAG_PROPERTY):
                    formatting.clearBackground()
            if vertical:
                formatting.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
            return formatting

        self._rewrite_formats(start, end, stripped)

    def _clear_selection_format(self) -> None:
        cursor = self._format_cursor(select_word=True)
        if cursor is None or not cursor.hasSelection():
            return
        self._strip_formats(
            cursor.selectionStart(), cursor.selectionEnd(), tags=True, highlights=True, vertical=True
        )
        self.editor.setCurrentCharFormat(untagged_format(self.editor.currentCharFormat()))
        self.superscript_button.setChecked(False)
        self.subscript_button.setChecked(False)

    def _remove_tag(self, span: TagSpan) -> None:
        self._strip_formats(span.start, span.end, tags=True, highlights=False, vertical=False)
        self.statusBar().showMessage(f"Removed the tag {span.label}.", 3_000)

    def _extend_editor_menu(self, menu: QMenu, cursor: QTextCursor) -> None:
        """Offer tagging and tag removal in the editor's right-click menu."""

        if not self.editor.isEnabled():
            return
        menu.addSeparator()
        tag_menu = menu.addMenu("Tag as")
        for label in self._tag_choices():
            tag_menu.addAction(label, lambda _checked=False, value=label: self._apply_tag(value))
        tag_menu.addSeparator()
        tag_menu.addAction("New tag…", self._tag_selection)
        if cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            touched = [span for span in self._editor_tags if span.start < end and start < span.end]
        else:
            position = cursor.position()
            touched = [span for span in self._editor_tags if span.start <= position <= span.end]
        for span in touched:
            words = " ".join(span.text.split())
            menu.addAction(
                f"Remove tag “{span.label}” from “{words}”",
                lambda _checked=False, value=span: self._remove_tag(value),
            )

    @Slot()
    def _update_tag_panel(self) -> None:
        if not self.editor.isEnabled() or self.current_line_id is None:
            self._editor_tags = []
            self.tag_panel.clear()
            return
        self._editor_tags = tag_spans(self.editor.toPlainText(), self._collect_annotations())
        if not self._editor_tags:
            self.tag_panel.setText(
                "No tags in this line. Select a word and choose <b>Tag…</b> "
                f"({html.escape(shortcut_text(SHORTCUTS['tag'][0]))}) or right-click it."
            )
            return
        entries = []
        for index, span in enumerate(self._editor_tags):
            words = html.escape(" ".join(span.text.split()))
            entries.append(
                f'{tag_label_html(span.label, span.color)}&nbsp;'
                f'<a href="select:{index}" style="color:#20252B; text-decoration:none;">{words}</a>'
                f'&nbsp;<a href="remove:{index}" style="color:#9A6F6B; text-decoration:none;">✕</a>'
            )
        self.tag_panel.setText("Tags: " + " &nbsp;&nbsp; ".join(entries))
        self.tag_panel.setToolTip("Click tagged words to select them; ✕ removes that tag.")

    @Slot(str)
    def _tag_panel_link(self, link: str) -> None:
        kind, _separator, number = link.partition(":")
        try:
            span = self._editor_tags[int(number)]
        except (ValueError, IndexError):
            return
        if kind == "remove":
            self._remove_tag(span)
        elif kind == "select":
            self._select_editor_range(span.start, span.end)

    def _select_editor_range(self, start: int, end: int) -> None:
        length = len(self.editor.toPlainText())
        cursor = self.editor.textCursor()
        cursor.setPosition(min(start, length))
        cursor.setPosition(min(end, length), QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _insert_character(self, character: str) -> None:
        if not self.editor.isEnabled():
            return
        self.editor.prepare_insertion()
        cursor = self._format_cursor()
        if cursor is None:
            return
        cursor.insertText(character)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()

    @Slot(int)
    def _set_editor_font_size(self, point_size: int) -> None:
        font = self.editor.font()
        font.setPointSize(point_size)
        self.editor.setFont(font)
        QSettings().setValue("editor/font_size", point_size)

    def _collect_annotations(self) -> list[dict[str, object]]:
        annotations: list[dict[str, object]] = []
        block = self.editor.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                iterator += 1
                if not fragment.isValid() or not fragment.text():
                    continue
                start = fragment.position()
                end = start + fragment.length()
                formatting = fragment.charFormat()
                vertical = formatting.verticalAlignment()
                if vertical == QTextCharFormat.VerticalAlignment.AlignSuperScript:
                    annotations.append({"start": start, "end": end, "kind": "superscript"})
                elif vertical == QTextCharFormat.VerticalAlignment.AlignSubScript:
                    annotations.append({"start": start, "end": end, "kind": "subscript"})
                if formatting.hasProperty(TAG_PROPERTY):
                    annotations.append({
                        "start": start,
                        "end": end,
                        "kind": "tag",
                        "label": str(formatting.property(TAG_PROPERTY)),
                        "color": str(formatting.property(TAG_COLOR_PROPERTY) or "#FFF0A8"),
                    })
                # Recorded independently, so a highlight survives tagging and untagging.
                if formatting.hasProperty(HIGHLIGHT_PROPERTY):
                    annotations.append({
                        "start": start,
                        "end": end,
                        "kind": "highlight",
                        "color": str(formatting.property(HIGHLIGHT_PROPERTY) or HIGHLIGHT_COLOR),
                    })
            block = block.next()

        # Join pieces of one annotation that Qt split into several fragments, e.g. a tag
        # whose middle letter is superscript.
        merged: list[dict[str, object]] = []
        latest: dict[tuple, dict[str, object]] = {}
        for annotation in annotations:
            identity = tuple(
                sorted((key, value) for key, value in annotation.items() if key not in {"start", "end"})
            )
            previous = latest.get(identity)
            if previous is not None and previous["end"] == annotation["start"]:
                previous["end"] = annotation["end"]
            else:
                latest[identity] = dict(annotation)
                merged.append(latest[identity])
        return merged

    def _apply_annotations(self, annotations: list[dict[str, object]]) -> None:
        length = len(self.editor.toPlainText())
        # Tags last, so their color shows over a highlight on the same words.
        ordered = sorted(
            annotations, key=lambda item: isinstance(item, dict) and item.get("kind") == "tag"
        )
        for annotation in ordered:
            try:
                start = max(0, min(length, int(annotation["start"])))
                end = max(start, min(length, int(annotation["end"])))
                kind = str(annotation["kind"])
            except (KeyError, TypeError, ValueError):
                continue
            if start == end:
                continue
            cursor = self.editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            formatting = QTextCharFormat()
            if kind == "superscript":
                formatting.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
            elif kind == "subscript":
                formatting.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
            elif kind == "tag":
                label = str(annotation.get("label") or "Tag")
                stored = annotation.get("color")
                formatting = tag_format(label, tag_color(label, stored))
                # Keep the stored color so that merely viewing a line never rewrites it.
                if isinstance(stored, str) and stored:
                    formatting.setProperty(TAG_COLOR_PROPERTY, stored)
            elif kind == "highlight":
                color = str(annotation.get("color") or HIGHLIGHT_COLOR)
                formatting.setProperty(HIGHLIGHT_PROPERTY, color)
                formatting.setBackground(QColor(color))
            else:
                continue
            cursor.mergeCharFormat(formatting)

    def _select_line(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None or not self.project:
            return
        self.save_current_edit()
        self.current_line_id = int(current.data(Qt.UserRole))
        line = self.project.line(self.current_line_id)
        self.current_line_text = line.display_text
        self.current_line_annotations = line.annotations
        self.editor.blockSignals(True)
        # setPlainText gives the new text the caret's current format; without this reset
        # a tag, highlight, or superscript at the caret in the previous line would be
        # copied onto the entire newly selected line (and saved when leaving it).
        self.editor.setCurrentCharFormat(QTextCharFormat())
        self.editor.setPlainText(line.display_text)
        self._apply_annotations(line.annotations)
        self.editor.setEnabled(True)
        self.editor.blockSignals(False)
        self.superscript_button.setChecked(False)
        self.subscript_button.setChecked(False)
        self._update_tag_panel()
        self._update_overlay_highlights()

    @Slot(object)
    def _hover_line(self, line_id: int | None) -> None:
        self._hovered_line_id = line_id
        self._update_overlay_highlights()

    def _update_overlay_highlights(self) -> None:
        for overlay in self._overlays:
            line_id = overlay.data(0)
            if line_id == self.current_line_id:
                overlay.setBrush(QBrush(QColor(45, 108, 223, 64)))
                overlay.setPen(QPen(QColor("#2D6CDF"), 3))
            elif line_id == self._hovered_line_id:
                overlay.setBrush(QBrush(QColor(184, 148, 145, 82)))
                overlay.setPen(QPen(QColor("#9A6F6B"), 3))
            else:
                overlay.setBrush(QBrush(QColor(0, 0, 0, 0)))
                overlay.setPen(QPen(QColor("#9A6F6B"), 2))

    def _schedule_autosave(self) -> None:
        if self.autosave_enabled and self.current_line_id is not None and self.project:
            self._edit_timer.start()

    @Slot()
    def save_current_edit(self) -> None:
        self._edit_timer.stop()
        if self.current_line_id is None or not self.project:
            return
        text = self.editor.toPlainText()
        annotations = self._collect_annotations()
        if text == self.current_line_text and annotations == self.current_line_annotations:
            return
        if self.project.correct_line(self.current_line_id, text, annotations):
            self.current_line_text = text
            self.current_line_annotations = annotations
            self._update_line_item(self.current_line_id)

    def _describe_line_item(self, item: QListWidgetItem, line) -> None:
        """Show order, confidence band, verification, and problems for one listed line."""

        label = self.thresholds.classify(line.confidence).value
        verified = line.review_status == ReviewStatus.VERIFIED
        mark = "✓ " if verified else ""
        prefix = f"{line.position + 1:03d}  {mark}[{label.replace('_', ' ')}]  "
        item.setText(prefix + line.display_text)
        # Rich rendering shows formatting and names each tag directly at its words.
        item.setData(
            LINE_HTML_ROLE,
            f'<span style="color:#56616D;">{html.escape(prefix)}</span>'
            + annotated_html(line.display_text, line.annotations),
        )
        item.setData(NEEDS_REVIEW_ROLE, not verified and label != "higher")
        color = CONFIDENCE_COLORS.get(label)
        item.setBackground(QBrush(QColor(color)) if color else QBrush())
        notes = []
        if verified:
            notes.append("Manually verified.")
        if line.recognition_error:
            notes.append(f"Recognition failed: {line.recognition_error}")
        if line.truncated:
            notes.append("The model stopped at its length limit; the end of this line may be missing.")
        tags = tag_summary(line.display_text, line.annotations)
        if tags:
            notes.append(f"Tags: {tags}")
        item.setToolTip("\n".join(notes))

    def _update_line_item(self, line_id: int) -> None:
        if not self.project:
            return
        for row in range(self.line_list.count()):
            item = self.line_list.item(row)
            if int(item.data(Qt.UserRole)) == line_id:
                self._describe_line_item(item, self.project.line(line_id))
                return

    @Slot()
    def _store_list_order(self) -> None:
        """Persist the order shown in the line list (after the reviewer dragged a line)."""

        if not self.project:
            return
        line_ids = [
            int(self.line_list.item(row).data(Qt.UserRole)) for row in range(self.line_list.count())
        ]
        self._set_line_order(line_ids)

    def _set_line_order(self, line_ids: list[int]) -> None:
        try:
            self.project.set_line_order(self.current_page, line_ids)
        except ValueError as error:
            self._error("The reading order could not be changed", str(error))
        self._refresh_lines()
        current = self.line_list.currentItem()
        if current:
            self.line_list.scrollToItem(current)
        self.status_label.setText(
            "Reading order updated; exports use this order. "
            "Review > Reading order > Restore detected order undoes it."
        )

    def _move_current_line(self, step: int) -> None:
        row = self.line_list.currentRow()
        target = row + step
        if not self.project or row < 0:
            self.statusBar().showMessage("Select the line to move first.", 4_000)
            return
        if not 0 <= target < self.line_list.count():
            return
        line_ids = [
            int(self.line_list.item(index).data(Qt.UserRole))
            for index in range(self.line_list.count())
        ]
        line_ids.insert(target, line_ids.pop(row))
        self._set_line_order(line_ids)

    @Slot()
    def _restore_detected_order(self) -> None:
        if not self.project:
            return
        self.project.reset_line_order(self.current_page)
        self._refresh_lines()
        self.status_label.setText("This page uses the detected reading order again.")

    def _line_list_menu(self, point) -> None:
        item = self.line_list.itemAt(point)
        if item is None or not self.project:
            return
        self.line_list.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction(self.actions["Move line up"])
        menu.addAction(self.actions["Move line down"])
        menu.addAction(self.actions["Restore detected order"])
        menu.addSeparator()
        menu.addAction(self.actions["Mark selected line verified"])
        menu.exec(self.line_list.viewport().mapToGlobal(point))

    @Slot()
    def show_tag_overview(self) -> None:
        if not self.project:
            self._error("No project is open", "Open a project first.")
            return
        self.save_current_edit()
        entries = [
            {
                "label": span.label,
                "text": " ".join(span.text.split()),
                "color": span.color,
                "page": line.page_number,
                "line": line.position + 1,
                "line_id": line.id,
                "start": span.start,
                "end": span.end,
            }
            for line in self.project.tagged_lines()
            for span in tag_spans(line.display_text, line.annotations)
        ]
        if self._tag_overview:
            self._tag_overview.close()
        dialog = TagOverviewDialog(entries, self)
        dialog.jump_requested.connect(self._jump_to_tag)
        dialog.finished.connect(lambda _result: setattr(self, "_tag_overview", None))
        self._tag_overview = dialog
        dialog.show()

    @Slot(object)
    def _jump_to_tag(self, entry: dict) -> None:
        if not self.project:
            return
        try:
            line = self.project.line(int(entry["line_id"]))
        except KeyError:
            self._error(
                "This tag is no longer available",
                "The line was replaced, for example by re-segmentation. Open the tag list again.",
            )
            return
        self._go_to_page(line.page_number)
        for row in range(self.line_list.count()):
            if int(self.line_list.item(row).data(Qt.UserRole)) == line.id:
                self.line_list.setCurrentRow(row)
                self.line_list.scrollToItem(self.line_list.item(row))
                break
        self._select_editor_range(int(entry["start"]), int(entry["end"]))
        self.activateWindow()

    @Slot()
    def _verify_line(self) -> None:
        if self.project and self.current_line_id is not None:
            # Verification must apply to the text on screen, not a pending autosave.
            self.save_current_edit()
            self.project.set_review_status(self.current_line_id, ReviewStatus.VERIFIED)
            self._update_line_item(self.current_line_id)
            self.status_label.setText("Selected line marked as manually verified.")

    @Slot()
    def _next_uncertain(self) -> None:
        start = self.line_list.currentRow() + 1
        for row in range(start, self.line_list.count()):
            if self.line_list.item(row).data(NEEDS_REVIEW_ROLE):
                self.line_list.setCurrentRow(row)
                return
        self.status_label.setText("No later unverified uncertain line on this page.")

    @Slot()
    def evaluate_corrections(self) -> None:
        if not self.project:
            self._error("No project is open", "Open a project first.")
            return
        self.save_current_edit()
        report = evaluate_project_lines(self.project.lines())
        verified = int(report["verified_reference_lines"])
        if not verified:
            QMessageBox.information(
                self,
                "No verified ground truth yet",
                "This project contains no human-verified lines. Model scores alone cannot measure "
                "transcription accuracy or calibrate the uncertainty labels. Correct a representative "
                "sample, compare every line with the image, and mark those lines as verified first.",
            )
            return
        cer = report["cer"]["rate"] * 100
        wer = report["wer"]["rate"] * 100
        exact = report["exact_line_rate"] * 100
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Verified-line evaluation")
        dialog.setIcon(QMessageBox.Information)
        dialog.setText(
            f"{verified} verified line(s): CER {cer:.2f}%, WER {wer:.2f}%, "
            f"exact lines {exact:.1f}%."
        )
        dialog.setInformativeText(
            "These results apply only to the verified sample. Expand it across pages, handwriting "
            "styles, short fragments, and difficult lines before comparing models."
        )
        dialog.setDetailedText(json.dumps(report, ensure_ascii=False, indent=2))
        dialog.exec()

    def _export_default_path(self, suffix: str) -> str:
        """Suggest a file beside the project; a bare name would resolve against the working
        directory, which is "/" for a Finder-launched Mac app and the install folder on Windows."""

        if self.project_path:
            return str(self.project_path.with_name(f"{self.project_path.stem}{suffix}"))
        return str(Path.home() / f"transcription{suffix}")

    @Slot()
    def export_project(self, requested_suffix: str | None = None) -> None:
        if not self.project:
            self._error("No project is open", "Open a project before exporting.")
            return
        if not self.project.lines():
            self._error("Nothing to export", "Transcribe at least one page first.")
            return
        formats = {
            ".txt": ("Plain text", "Text (*.txt)"),
            ".docx": ("Word document", "Word (*.docx)"),
            ".csv": ("CSV table", "CSV (*.csv)"),
            ".xlsx": ("Excel workbook", "Excel (*.xlsx)"),
            ".json": ("Research JSON", "JSON (*.json)"),
        }
        suffix = requested_suffix if requested_suffix in formats else ".txt"
        description, file_filter = formats[suffix]
        filename, selected = QFileDialog.getSaveFileName(
            self, f"Export {description}", self._export_default_path(f"{suffix}"), file_filter
        )
        if not filename:
            return
        try:
            if not Path(filename).suffix:
                filename += suffix
            suffix = Path(filename).suffix.lower()
            if suffix == ".txt":
                export_text(self.project, filename)
            elif suffix == ".docx":
                export_docx(self.project, filename)
            elif suffix == ".csv":
                export_csv(self.project, filename)
            elif suffix == ".xlsx":
                export_xlsx(self.project, filename)
            elif suffix == ".json":
                export_json(self.project, filename)
            else:
                raise ValueError(f"Unsupported export format: {suffix or selected}")
            self.status_label.setText(f"Exported {Path(filename).name}")
        except Exception as error:
            self._error("The export could not be created", str(error))

    @Slot()
    def export_ground_truth_bundle(self) -> None:
        if not self.project:
            self._error("No project is open", "Open a project first.")
            return
        document = self.project.document()
        if not document:
            self._error("The project is incomplete", "No source document is recorded.")
            return
        dialog = GroundTruthDialog(int(document["page_count"]), self.current_page, self)
        if not dialog.exec():
            return
        try:
            references = [index + 1 for index in parse_page_range(
                dialog.references.text(), int(document["page_count"])
            )]
            targets = [index + 1 for index in parse_page_range(
                dialog.targets.text(), int(document["page_count"])
            )]
        except PageRangeError as error:
            self._error("Invalid page range", str(error))
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export ground-truth bundle",
            self._export_default_path("-ground-truth.zip"),
            "ZIP archive (*.zip)",
        )
        if not destination:
            return
        if not Path(destination).suffix:
            destination += ".zip"
        try:
            manifest = export_training_bundle(self.project, destination, references, targets)
        except GroundTruthError as error:
            self._error("Ground truth is not ready", str(error))
            return
        except Exception as error:
            self._error("The training bundle could not be created", str(error), exception_details(error))
            return
        QMessageBox.information(
            self,
            "Ground-truth bundle exported",
            f"Exported {manifest['line_count']} verified line(s) from page(s) "
            f"{', '.join(map(str, references))}. The manifest records intended target page(s) "
            f"{', '.join(map(str, targets))}.\n\n"
            "Fine-tune in a CUDA environment with held-out validation pages, then evaluate the adapted "
            "checkpoint before using it on the target range.",
        )

    def about(self) -> None:
        models = "\n".join(
            f"• {spec.model_id}\n  revision {spec.revision}"
            for spec in MODEL_CATALOG
        )
        QMessageBox.about(
            self, "About KurrentScholar",
            f"KurrentScholar {__version__}\n\nOffline historical handwriting research assistant.\n\n"
            f"Available pinned recognition models:\n{models}\n\n"
            "Models developed by Digital Humanities at the University of Bern and their collaborators; "
            "KurrentScholar did not develop or train them. MIT-licensed application and models."
        )

    @Slot()
    def show_diagnostic_log(self) -> None:
        QMessageBox.information(
            self,
            "Diagnostic logs",
            "KurrentScholar records application stages, recoverable errors, Qt warnings, background "
            "thread failures, fatal crashes, and GUI stalls locally.\n\n"
            f"Application log:\n{log_path()}\n\n"
            f"Crash and native-fault log:\n{log_path().parent / CRASH_LOG_FILE_NAME}\n\n"
            "These files may contain local filenames but never manuscript contents.",
        )

    def _error(self, title: str, message: str, details: str = "") -> None:
        LOGGER.error("UI error: %s: %s\n%s", title, message, details)
        dialog = QMessageBox(QMessageBox.Critical, title, message, parent=self)
        if details:
            dialog.setDetailedText(details)
        dialog.exec()

    def closeEvent(self, event) -> None:
        if self._install_running():
            QMessageBox.information(
                self,
                "Model installation is active",
                "Wait for the current model download to finish before closing KurrentScholar. "
                "Completed files will be reused if the download is interrupted externally.",
            )
            event.ignore()
            return
        if self._thread and self._thread.isRunning():
            QMessageBox.information(
                self,
                "Transcription is active",
                "Cancel transcription and wait for the current line to finish before closing.",
            )
            event.ignore()
            return
        self.save_current_edit()
        if self.project:
            self.project.close()
        event.accept()

