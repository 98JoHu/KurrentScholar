from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from statistics import median

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, QRectF, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kurrentscholar import __version__
from kurrentscholar.constants import (
    APP_NAME,
    DEFAULT_MODEL,
    MODEL_CATALOG,
    ModelSpec,
    find_model,
)
from kurrentscholar.diagnostics import exception_details, log_path
from kurrentscholar.document_processing import DocumentRenderer, PageRangeError, parse_page_range
from kurrentscholar.domain import ConfidenceThresholds, ReviewStatus
from kurrentscholar.evaluation import evaluate_project_lines
from kurrentscholar.exports import (
    ExportOptions,
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
    LocalHelpDialog,
    ModelManagerDialog,
    TutorialDialog,
)

LOGGER = logging.getLogger(f"{APP_NAME}.ui")


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
                    model_id=self.model_spec.model_id,
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
                    project.upsert_page(page_index + 1, rendered.image.width, rendered.image.height,
                                        self.dpi, status=status, error=error)
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
                        crop = rendered.image.crop((box.x, box.y, box.right, box.bottom))
                        try:
                            LOGGER.info(
                                "Recognizing page %s line %s", page_index + 1, line_number + 1
                            )
                            result = recognizer.recognize_line(crop)
                            line_id = project.add_line(
                                page_index + 1, detected.reading_order, box, result.text,
                                result.line_confidence, result.token_probabilities,
                                result.token_ids, result.truncated,
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
                                recognition_error=str(error),
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
        self.thresholds = ConfidenceThresholds()
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._processing_progress: QProgressDialog | None = None
        self._install_thread: QThread | None = None
        self._install_worker: ModelInstallWorker | None = None
        self._install_progress: QProgressDialog | None = None
        self._install_progress_timer: QTimer | None = None
        self._install_phase = "idle"
        self._model_manager_dialog: ModelManagerDialog | None = None
        self._help_dialog: LocalHelpDialog | None = None
        self._last_resegmentation_backup: Path | None = None
        self._edit_timer = QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(700)
        self._edit_timer.timeout.connect(self.save_current_edit)
        self._display_scale_x = 1.0
        self._display_scale_y = 1.0
        self.actions: dict[str, QAction] = {}
        self._overlays: list[QGraphicsRectItem] = []
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
        self.viewer.setRenderHints(self.viewer.renderHints())
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.line_list = QListWidget()
        self.line_list.setObjectName("lineList")
        self.line_list.currentItemChanged.connect(self._select_line)
        self.editor = QTextEdit()
        self.editor.setObjectName("transcriptionEditor")
        self.editor.setPlaceholderText("Select a line to review or correct its transcription.")
        self.editor.textChanged.connect(self._schedule_autosave)
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
        right_layout.addWidget(self.line_list, 2)
        right_layout.addWidget(self.editor, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(verify)
        buttons.addWidget(next_uncertain)
        right_layout.addLayout(buttons)

        splitter = QSplitter()
        splitter.addWidget(self.viewer)
        splitter.addWidget(right)
        splitter.setSizes([760, 520])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Ready")

    def _apply_style(self) -> None:
        """A restrained Material-inspired palette adapted from OpenEarable's visual language."""

        self.setStyleSheet(
            """
            QMainWindow { background: #F4F7FB; color: #20252B; }
            QMenuBar { background: #FFFFFF; padding: 4px 8px; border-bottom: 1px solid #E2E7ED; }
            QMenuBar::item { padding: 7px 10px; border-radius: 7px; }
            QMenuBar::item:selected { background: #F0E7E6; }
            QMenu { background: #FFFFFF; border: 1px solid #DDE3EA; padding: 6px; }
            QMenu::item { padding: 7px 26px 7px 10px; border-radius: 6px; }
            QMenu::item:selected { background: #F0E7E6; color: #5E3F3C; }
            QToolBar { background: #FFFFFF; border: 0; border-bottom: 1px solid #E2E7ED; spacing: 6px; padding: 7px 10px; }
            QToolButton, QPushButton { background: #F0E7E6; color: #5E3F3C; border: 1px solid #DECBC9; border-radius: 10px; padding: 7px 12px; font-weight: 600; }
            QToolButton:hover, QPushButton:hover { background: #E7D7D5; }
            QToolButton:pressed, QPushButton:pressed { background: #D9C2BF; }
            QToolButton:disabled, QPushButton:disabled { background: #EEF0F3; color: #9AA2AB; border-color: #E1E5E9; }
            QGraphicsView, QListWidget, QTextEdit, QTextBrowser, QTableWidget, QLineEdit { background: #FFFFFF; border: 1px solid #DDE3EA; border-radius: 12px; selection-background-color: #DCC8C5; selection-color: #20252B; }
            QGraphicsView { margin: 8px 4px 8px 8px; }
            QWidget#reviewCard { background: #FFFFFF; border: 1px solid #DDE3EA; border-radius: 18px; }
            QLabel#contextStatus { color: #56616D; padding: 8px 4px; }
            QLabel#tutorialHeading { font-size: 24px; font-weight: 700; color: #5E3F3C; }
            QProgressDialog { background: #F4F7FB; }
            QHeaderView::section { background: #F0E7E6; color: #5E3F3C; padding: 7px; border: 0; border-right: 1px solid #DECBC9; font-weight: 600; }
            QStatusBar { background: #FFFFFF; border-top: 1px solid #E2E7ED; color: #68737E; }
            """
        )

    def _run_onboarding(self) -> None:
        settings = QSettings()
        if not settings.value("onboarding/tutorial_seen", False, type=bool):
            TutorialDialog(self).exec()
            settings.setValue("onboarding/tutorial_seen", True)
        if not self.model_manager.status().installed:
            self._offer_model_installation()

    @Slot()
    def show_tutorial(self) -> None:
        TutorialDialog(self).exec()

    def _build_actions(self) -> None:
        def action(name, callback, shortcut=None, tip=""):
            created = QAction(name, self)
            created.triggered.connect(callback)
            if shortcut:
                created.setShortcut(shortcut)
            if tip:
                created.setStatusTip(tip)
            self.actions[name] = created
            return created

        open_document = action("Open document", self.open_document, QKeySequence.Open)
        open_project = action("Open project", self.open_project, "Ctrl+Shift+O")
        previous = action("Previous page", lambda: self._change_page(-1), "PgUp")
        next_page = action("Next page", lambda: self._change_page(1), "PgDown")
        current = action("Transcribe current page", self.transcribe_current_page, "Ctrl+T")
        page_range = action("Transcribe page range…", self.transcribe_page_range, "Ctrl+Shift+T")
        all_pages = action("Transcribe full document", self.transcribe_all)
        self.actions["Transcribe"] = all_pages  # compatibility with earlier UI/tests
        resegment = action("Re-segment", self.resegment)
        select_model = action("Recognition model", self.select_recognition_model)
        manage_models = action("Model Manager", self.show_model_manager)
        self.actions["Install model"] = manage_models
        save = action("Save", self.save_current_edit, QKeySequence.Save)
        verify = action("Mark selected line verified", self._verify_line, "Ctrl+Shift+V")
        uncertain = action("Next uncertain line", self._next_uncertain, "F6")
        evaluate = action("Evaluate corrections", self.evaluate_corrections)
        ground_truth = action("Export ground-truth bundle…", self.export_ground_truth_bundle)
        zoom_in = action("Zoom in", lambda: self.viewer.scale(1.2, 1.2), QKeySequence.ZoomIn)
        zoom_out = action("Zoom out", lambda: self.viewer.scale(1 / 1.2, 1 / 1.2), QKeySequence.ZoomOut)
        zoom_fit = action("Fit page", lambda: self.viewer.fitInView(self.pixmap_item, Qt.KeepAspectRatio))
        tutorial = action("Tutorial", self.show_tutorial)
        local_help = action("Local Help Assistant", self.show_local_help)
        diagnostic = action("Diagnostic log", self.show_diagnostic_log)
        about = action("About", self.about)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([open_document, open_project])
        export_menu = file_menu.addMenu("Export")
        for label, suffix in (
            ("Plain text…", ".txt"), ("Word document…", ".docx"),
            ("CSV table…", ".csv"), ("Excel workbook…", ".xlsx"),
            ("Research JSON…", ".json"),
        ):
            export_menu.addAction(action(f"Export {label}", lambda _checked=False, s=suffix: self.export_project(s)))
        file_menu.addSeparator()
        file_menu.addAction(action("Exit", self.close, QKeySequence.Quit))

        transcription_menu = self.menuBar().addMenu("&Transcription")
        transcription_menu.addActions([current, page_range, all_pages])
        transcription_menu.addSeparator()
        transcription_menu.addAction(resegment)

        review_menu = self.menuBar().addMenu("&Review")
        review_menu.addActions([save, verify, uncertain, evaluate])
        review_menu.addSeparator()
        review_menu.addAction(ground_truth)

        models_menu = self.menuBar().addMenu("&Models")
        models_menu.addActions([manage_models, select_model])

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions([previous, next_page])
        view_menu.addSeparator()
        view_menu.addActions([zoom_in, zoom_out, zoom_fit])

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addActions([tutorial, local_help, diagnostic])
        help_menu.addSeparator()
        help_menu.addAction(about)

        toolbar = QToolBar("Primary actions")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        toolbar.addAction(open_document)
        toolbar.addAction(open_project)
        toolbar.addSeparator()
        toolbar.addAction(previous)
        toolbar.addAction(next_page)
        toolbar.addSeparator()
        transcribe_button = QToolButton()
        transcribe_button.setText("Transcribe")
        transcribe_button.setToolTip("Choose which pages to transcribe")
        transcribe_button.setPopupMode(QToolButton.InstantPopup)
        transcribe_button.setMenu(transcription_menu)
        toolbar.addWidget(transcribe_button)
        toolbar.addAction(save)
        self._update_navigation_actions()

    def _update_navigation_actions(self) -> None:
        document = self.project.document() if self.project else None
        page_count = int(document["page_count"]) if document else 0
        self.actions["Previous page"].setEnabled(self.current_page > 1)
        self.actions["Next page"].setEnabled(0 < self.current_page < page_count)

    def _change_page(self, change: int) -> None:
        if not self.project:
            return
        document = self.project.document()
        if not document:
            return
        target = self.current_page + change
        if not 1 <= target <= document["page_count"]:
            return
        self.save_current_edit()
        self.current_page = target
        self._render_page()
        self._refresh_lines()
        self.status_label.setText(f"Page {self.current_page} of {document['page_count']}.")

    def _show_welcome_status(self) -> None:
        status = self.model_manager.status()
        if status.installed:
            text = "Handwriting model installed. Open a PDF or archival image to begin."
        else:
            text = ("Welcome. The separate 1.34 GB handwriting model is not installed. Choose ‘Install model’ "
                    "once while online; documents are never uploaded and later transcription is offline.")
        self.status_label.setText(text)

    def _offer_model_installation(self) -> None:
        if self.model_manager.status().installed or (
            self._install_thread and self._install_thread.isRunning()
        ):
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
        rendered = self.renderer.render(document["source_path"], self.current_page - 1, dpi=150)
        page = self.project.page(self.current_page)
        if page:
            self._display_scale_x = rendered.image.width / page["width"]
            self._display_scale_y = rendered.image.height / page["height"]
        else:
            self._display_scale_x = self._display_scale_y = 1.0
        qt_image = ImageQt(rendered.image)
        self.pixmap_item.setPixmap(QPixmap.fromImage(qt_image))
        self.scene.setSceneRect(QRectF(self.pixmap_item.boundingRect()))
        self.viewer.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        self._update_navigation_actions()

    def _refresh_lines(self, preserve_selection: bool = True) -> None:
        selected_id = self.current_line_id if preserve_selection else None
        if preserve_selection:
            self.save_current_edit()
        self.line_list.blockSignals(True)
        self._edit_timer.stop()
        self.current_line_id = None
        self.current_line_text = None
        self.line_list.clear()
        for overlay in self._overlays:
            self.scene.removeItem(overlay)
        self._overlays.clear()
        selected_row = -1
        if self.project:
            for line in self.project.lines(self.current_page):
                label = self.thresholds.classify(line.confidence)
                item = QListWidgetItem(
                    f"{line.reading_order + 1:03d}  [{label.value.replace('_', ' ')}]  {line.display_text}"
                )
                item.setData(Qt.UserRole, line.id)
                color = {"moderate": "#FFF0C2", "high_uncertainty": "#F7D8C4",
                         "very_high_uncertainty": "#F2B8B5", "unavailable": "#E5E8EB"}.get(label.value)
                if color:
                    item.setBackground(QBrush(QColor(color)))
                self.line_list.addItem(item)
                if line.id == selected_id:
                    selected_row = self.line_list.count() - 1
                box = line.bbox
                rect = QGraphicsRectItem(
                    box.x * self._display_scale_x,
                    box.y * self._display_scale_y,
                    box.width * self._display_scale_x,
                    box.height * self._display_scale_y,
                )
                rect.setPen(QPen(QColor("#9A6F6B"), 2))
                rect.setData(0, line.id)
                self.scene.addItem(rect)
                self._overlays.append(rect)
        self.line_list.blockSignals(False)
        if selected_row >= 0:
            self.line_list.setCurrentRow(selected_row)
        else:
            self.editor.blockSignals(True)
            self.editor.clear()
            self.editor.blockSignals(False)

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
        manager = ModelManager(spec=selected)
        if not manager.status().installed:
            self._error(
                "The selected model is not installed",
                f"Choose Install model, install ‘{selected.display_name}’, then select it again. "
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

    @Slot()
    def transcribe(self) -> None:
        self.transcribe_all()

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
        self.transcribe()

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
            "Transcribe",
            "Transcribe current page",
            "Transcribe page range…",
            "Re-segment",
            "Recognition model",
            "Model Manager",
        ):
            self.actions[name].setEnabled(not busy)

    @Slot()
    def install_model(self) -> None:
        self.show_model_manager()

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
        if self._help_dialog:
            self._help_dialog.refresh()
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
        if selected.kind != "recognition" or selected == current:
            return
        if not ModelManager(spec=selected).status().installed:
            self._error("The selected model is not installed", "Install it first.")
            return
        summary = self.project.transcription_summary()
        if summary["line_count"] and not self._backup_and_reset_transcription(
            f"Changing from ‘{current.display_name}’ to ‘{selected.display_name}’ requires "
            "replacing the current machine transcription.",
            operation="change recognition model",
            backup_suffix="before-model-change",
        ):
            return
        self.project.set_info({"model_id": selected.model_id, "model_revision": selected.revision})
        self.model_manager = ModelManager(spec=selected)
        self.status_label.setText(
            f"Recognition model changed to {selected.display_name}. Choose pages to transcribe."
        )
        if self._model_manager_dialog:
            self._model_manager_dialog.project_model = selected
            self._model_manager_dialog.refresh()

    @Slot()
    def show_local_help(self) -> None:
        if self._help_dialog:
            self._help_dialog.refresh()
            self._help_dialog.show()
            self._help_dialog.raise_()
            return
        dialog = LocalHelpDialog(self)
        dialog.install_requested.connect(self._install_selected_model)
        dialog.finished.connect(lambda _result: setattr(self, "_help_dialog", None))
        self._help_dialog = dialog
        dialog.show()

    def _start_model_installation(self) -> None:
        if self._install_thread and self._install_thread.isRunning():
            if self._install_progress:
                self._install_progress.show()
                self._install_progress.raise_()
            return
        self.actions["Install model"].setEnabled(False)
        progress = QProgressDialog("Starting model download…", "Hide", 0, 1000, self)
        progress.setWindowTitle(f"Installing {self.model_manager.spec.display_name}")
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
        self._install_worker = ModelInstallWorker(self.model_manager)
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
        status = self.model_manager.status()
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
        self.actions["Install model"].setEnabled(True)
        if self._model_manager_dialog:
            self._model_manager_dialog.refresh()
        if self._help_dialog:
            self._help_dialog.refresh()
        self.status_label.setText(f"{self.model_manager.spec.display_name} installed and ready offline.")
        QMessageBox.information(
            self,
            "Model installation complete",
            f"‘{self.model_manager.spec.display_name}’ was downloaded, verified, and is ready. "
            "It can now run without an internet connection.",
        )

    @Slot(str, str)
    def _model_install_failed(self, message: str, details: str) -> None:
        self._stop_install_progress_timer()
        if self._install_progress:
            self._install_progress.close()
        self._install_progress = None
        self._install_phase = "idle"
        self.actions["Install model"].setEnabled(True)
        if self._model_manager_dialog:
            self._model_manager_dialog.refresh()
        if self._help_dialog:
            self._help_dialog.refresh()
        LOGGER.error("Model installation failed: %s\n%s", message, details)
        self._error(
            "The model installation did not finish",
            f"No project data was affected. {message}\n\nYou can retry from the Install model button.",
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

    @Slot()
    def _update_model_download_progress(self) -> None:
        if not self._install_progress or self._install_phase != "download":
            return
        downloaded = self.model_manager.downloaded_bytes()
        required = self.model_manager.spec.required_bytes
        value = min(999, int(downloaded * 1000 / required))
        self._install_progress.setValue(value)
        gib = downloaded / (1024 ** 3)
        total_gib = required / (1024 ** 3)
        self._install_progress.setLabelText(
            f"Downloading the handwriting model: {gib:.2f} of {total_gib:.2f} GiB. "
            "Completed data is reused after interruptions."
        )

    def _select_line(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None or not self.project:
            return
        self.save_current_edit()
        self.current_line_id = int(current.data(Qt.UserRole))
        line = next(item for item in self.project.lines(self.current_page) if item.id == self.current_line_id)
        self.current_line_text = line.display_text
        self.editor.blockSignals(True)
        self.editor.setPlainText(line.display_text)
        self.editor.blockSignals(False)
        for overlay in self._overlays:
            selected = overlay.data(0) == line.id
            overlay.setBrush(QBrush(QColor(45, 108, 223, 60) if selected else QColor(0, 0, 0, 0)))

    def _schedule_autosave(self) -> None:
        if self.current_line_id is not None and self.project:
            self._edit_timer.start()

    @Slot()
    def save_current_edit(self) -> None:
        self._edit_timer.stop()
        if self.current_line_id is None or not self.project:
            return
        text = self.editor.toPlainText()
        if text == self.current_line_text:
            return
        if self.project.correct_line(self.current_line_id, text):
            self.current_line_text = text
            current = self.line_list.currentItem()
            if current:
                line = self.project.line(self.current_line_id)
                label = self.thresholds.classify(line.confidence).value.replace("_", " ")
                current.setText(f"{line.reading_order + 1:03d}  [{label}]  {line.display_text}")

    @Slot()
    def _verify_line(self) -> None:
        if self.project and self.current_line_id is not None:
            self.project.set_review_status(self.current_line_id, ReviewStatus.VERIFIED)
            self.status_label.setText("Selected line marked as manually verified.")

    @Slot()
    def _next_uncertain(self) -> None:
        start = self.line_list.currentRow() + 1
        for row in range(start, self.line_list.count()):
            if "[higher]" not in self.line_list.item(row).text():
                self.line_list.setCurrentRow(row)
                return
        self.status_label.setText("No later uncertain line on this page.")

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
            self, f"Export {description}", f"transcription{suffix}", file_filter
        )
        if not filename:
            return
        try:
            if not Path(filename).suffix:
                filename += suffix
            suffix = Path(filename).suffix.lower()
            options = ExportOptions(uncertainty_markers=True)
            {".txt": export_text, ".docx": export_docx}.get(suffix, lambda *_: None)(self.project, filename, options)
            if suffix == ".csv":
                export_csv(self.project, filename)
            elif suffix == ".xlsx":
                export_xlsx(self.project, filename)
            elif suffix == ".json":
                export_json(self.project, filename)
            elif suffix not in {".txt", ".docx"}:
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
            self, "Export ground-truth bundle", "kurrentscholar-ground-truth.zip", "ZIP archive (*.zip)"
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
            f"Crash and native-fault log:\n{log_path().parent / 'kurrentscholar-crash.log'}\n\n"
            "These files may contain local filenames but never manuscript contents.",
        )

    def _error(self, title: str, message: str, details: str = "") -> None:
        LOGGER.error("UI error: %s: %s\n%s", title, message, details)
        dialog = QMessageBox(QMessageBox.Critical, title, message, parent=self)
        if details:
            dialog.setDetailedText(details)
        dialog.exec()

    def closeEvent(self, event) -> None:
        if self._help_dialog and self._help_dialog.busy:
            QMessageBox.information(
                self,
                "Local helper is active",
                "Wait for the current local answer to finish before closing KurrentScholar.",
            )
            event.ignore()
            return
        if self._install_thread and self._install_thread.isRunning():
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

