from __future__ import annotations

import traceback
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, QRectF, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
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
    QVBoxLayout,
    QWidget,
)

from kurrentscholar.constants import MODEL_ID, MODEL_REVISION
from kurrentscholar.document_processing import DocumentRenderer
from kurrentscholar.domain import ConfidenceThresholds, ReviewStatus
from kurrentscholar.exports import ExportOptions, export_csv, export_docx, export_json, export_text
from kurrentscholar.projects import ProjectDatabase
from kurrentscholar.recognition import ModelManager, TrOCRBackend
from kurrentscholar.segmentation import ProjectionSegmenter


class ProcessingWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal()
    failed = Signal(str, str)

    def __init__(self, project_path: Path, pages: list[int], model_path: Path, dpi: int = 300) -> None:
        super().__init__()
        self.project_path = project_path
        self.pages = pages
        self.model_path = model_path
        self.dpi = dpi
        self.cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            with ProjectDatabase(self.project_path) as project:
                document = project.document()
                if not document:
                    raise ValueError("The project has no source document")
                renderer = DocumentRenderer()
                segmenter = ProjectionSegmenter()
                recognizer = TrOCRBackend(self.model_path)
                recognizer.load()
                project.set_info({
                    "model_id": MODEL_ID,
                    "model_revision": MODEL_REVISION,
                    "segmentation_backend": segmenter.backend_id,
                    "segmentation_version": segmenter.version,
                })
                total = len(self.pages)
                for position, page_index in enumerate(self.pages, start=1):
                    if self.cancelled:
                        break
                    self.progress.emit(position - 1, total, f"Rendering page {page_index + 1}")
                    rendered = renderer.render(document["source_path"], page_index, self.dpi)
                    lines = segmenter.detect_lines(rendered.image)
                    status = "segmented" if lines else "segmentation_failed"
                    error = None if lines else "No handwriting lines were detected; review this page manually."
                    project.upsert_page(page_index + 1, rendered.image.width, rendered.image.height,
                                        self.dpi, status=status, error=error)
                    for line_number, detected in enumerate(lines):
                        if self.cancelled:
                            break
                        self.progress.emit(position - 1, total,
                                           f"Page {page_index + 1}: line {line_number + 1}/{len(lines)}")
                        box = detected.bbox
                        crop = rendered.image.crop((box.x, box.y, box.right, box.bottom))
                        try:
                            result = recognizer.recognize_line(crop)
                            project.add_line(page_index + 1, detected.reading_order, box, result.text,
                                             result.line_confidence, result.token_probabilities,
                                             result.token_ids, result.truncated)
                        except Exception as error:  # keep failed regions visible
                            project.add_line(page_index + 1, detected.reading_order, box, "", None, [], [],
                                             recognition_error=str(error))
                    self.progress.emit(position, total, f"Saved page {page_index + 1}")
            self.finished.emit()
        except Exception as error:
            self.failed.emit(str(error), traceback.format_exc())

    @Slot()
    def cancel(self) -> None:
        self.cancelled = True


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
            self.manager.install(self.status.emit)
            self.finished.emit()
        except Exception as error:
            self.failed.emit(str(error), traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KurrentScholar")
        self.resize(1280, 800)
        self.setAcceptDrops(True)
        self.renderer = DocumentRenderer()
        self.model_manager = ModelManager()
        self.project: ProjectDatabase | None = None
        self.project_path: Path | None = None
        self.current_page = 1
        self.current_line_id: int | None = None
        self.thresholds = ConfidenceThresholds()
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._install_thread: QThread | None = None
        self._install_worker: ModelInstallWorker | None = None
        self._overlays: list[QGraphicsRectItem] = []
        self._build_ui()
        self._build_actions()
        self._show_welcome_status()

    def _build_ui(self) -> None:
        self.scene = QGraphicsScene(self)
        self.viewer = QGraphicsView(self.scene)
        self.viewer.setDragMode(QGraphicsView.ScrollHandDrag)
        self.viewer.setRenderHints(self.viewer.renderHints())
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.line_list = QListWidget()
        self.line_list.currentItemChanged.connect(self._select_line)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Select a line to review or correct its transcription.")
        self.editor.textChanged.connect(self._autosave_edit)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        verify = QPushButton("Mark selected line as verified")
        verify.clicked.connect(self._verify_line)
        next_uncertain = QPushButton("Next uncertain line")
        next_uncertain.clicked.connect(self._next_uncertain)
        right = QWidget()
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

    def _build_actions(self) -> None:
        toolbar = QToolBar("Main actions")
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        actions = [
            ("Open document", self.open_document, QKeySequence.Open),
            ("Open project", self.open_project, None),
            ("Transcribe", self.transcribe, None),
            ("Save", self.save_current_edit, QKeySequence.Save),
            ("Export", self.export_project, None),
            ("Install model", self.install_model, None),
            ("Zoom in", lambda: self.viewer.scale(1.2, 1.2), QKeySequence.ZoomIn),
            ("Zoom out", lambda: self.viewer.scale(1 / 1.2, 1 / 1.2), QKeySequence.ZoomOut),
            ("About", self.about, None),
        ]
        for text, callback, shortcut in actions:
            action = QAction(text, self)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(shortcut)
            toolbar.addAction(action)

    def _show_welcome_status(self) -> None:
        status = self.model_manager.status()
        if status.installed:
            text = "Handwriting model installed. Open a PDF or archival image to begin."
        else:
            text = ("Welcome. The separate 1.34 GB handwriting model is not installed. Choose ‘Install model’ "
                    "once while online; documents are never uploaded and later transcription is offline.")
        self.status_label.setText(text)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
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
        if self.project:
            self.project.close()
        self.project_path = Path(destination)
        self.project = ProjectDatabase(self.project_path, create=True)
        self.project.set_document(source, page_count)
        self.current_page = 1
        self._render_page()
        self._refresh_lines()
        self.status_label.setText(f"Project created. {page_count} page(s). Choose Transcribe when ready.")

    @Slot()
    def open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open project", "", "KurrentScholar (*.ksproj)")
        if filename:
            self._load_project(Path(filename))

    def _load_project(self, path: Path) -> None:
        try:
            if self.project:
                self.project.close()
            self.project = ProjectDatabase(path)
            self.project_path = path
            document = self.project.document()
            if not document or not Path(document["source_path"]).is_file():
                raise FileNotFoundError("The original document is missing. Relinking is not implemented yet.")
            self.current_page = 1
            self._render_page()
            self._refresh_lines()
            self.status_label.setText(f"Opened {path.name}")
        except Exception as error:
            self._error("The project could not be opened", str(error))

    def _render_page(self) -> None:
        if not self.project:
            return
        document = self.project.document()
        if not document:
            return
        rendered = self.renderer.render(document["source_path"], self.current_page - 1, dpi=150)
        qt_image = ImageQt(rendered.image)
        self.pixmap_item.setPixmap(QPixmap.fromImage(qt_image))
        self.scene.setSceneRect(QRectF(self.pixmap_item.boundingRect()))
        self.viewer.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def _refresh_lines(self) -> None:
        self.line_list.blockSignals(True)
        self.line_list.clear()
        for overlay in self._overlays:
            self.scene.removeItem(overlay)
        self._overlays.clear()
        if self.project:
            for line in self.project.lines(self.current_page):
                label = self.thresholds.classify(line.confidence)
                item = QListWidgetItem(
                    f"{line.reading_order + 1:03d}  [{label.value.replace('_', ' ')}]  {line.display_text}"
                )
                item.setData(Qt.UserRole, line.id)
                color = {"moderate": "#f2c94c", "high_uncertainty": "#f2994a",
                         "very_high_uncertainty": "#eb5757", "unavailable": "#bdbdbd"}.get(label.value)
                if color:
                    item.setBackground(QBrush(QColor(color)))
                self.line_list.addItem(item)
                box = line.bbox
                rect = QGraphicsRectItem(box.x / 2, box.y / 2, box.width / 2, box.height / 2)
                rect.setPen(QPen(QColor("#2d6cdf"), 2))
                rect.setData(0, line.id)
                self.scene.addItem(rect)
                self._overlays.append(rect)
        self.line_list.blockSignals(False)

    @Slot()
    def transcribe(self) -> None:
        if not self.project or not self.project_path:
            self._error("No project is open", "Open a manuscript first.")
            return
        status = self.model_manager.status()
        if not status.installed:
            self._error("The handwriting model is not installed", "Choose Install model and retry.")
            return
        document = self.project.document()
        pages = list(range(document["page_count"]))
        self.project.close()
        self.project = None
        self._thread = QThread(self)
        self._worker = ProcessingWorker(self.project_path, pages, status.path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        progress = QProgressDialog("Preparing transcription…", "Cancel", 0, len(pages), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.canceled.connect(self._worker.cancel)
        self._worker.progress.connect(lambda value, maximum, text: (
            progress.setMaximum(maximum), progress.setValue(value), progress.setLabelText(text)
        ))
        self._worker.finished.connect(lambda: self._processing_done(progress))
        self._worker.failed.connect(lambda message, details: self._processing_failed(progress, message, details))
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _processing_done(self, progress: QProgressDialog) -> None:
        progress.close()
        self.project = ProjectDatabase(self.project_path)
        self._refresh_lines()
        self.status_label.setText("Transcription stopped or completed; all completed lines were saved.")

    def _processing_failed(self, progress: QProgressDialog, message: str, details: str) -> None:
        progress.close()
        self.project = ProjectDatabase(self.project_path)
        self._error("Transcription could not continue", message, details)

    @Slot()
    def install_model(self) -> None:
        answer = QMessageBox.question(
            self,
            "Install handwriting model",
            "Download 1.34 GB of model files now? This contacts Hugging Face only for the model; no documents "
            "or transcriptions are sent. The pinned model is separate from KurrentScholar and works offline afterward.",
        )
        if answer != QMessageBox.Yes:
            return
        progress = QProgressDialog("Starting model download…", "Hide", 0, 0, self)
        progress.setWindowTitle("Installing handwriting model")
        progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False)
        progress.canceled.connect(progress.hide)
        progress.show()
        self._install_thread = QThread(self)
        self._install_worker = ModelInstallWorker(self.model_manager)
        self._install_worker.moveToThread(self._install_thread)
        self._install_thread.started.connect(self._install_worker.run)
        self._install_worker.status.connect(progress.setLabelText)
        self._install_worker.finished.connect(lambda: self._model_install_done(progress))
        self._install_worker.failed.connect(
            lambda message, details: self._model_install_failed(progress, message, details)
        )
        self._install_worker.finished.connect(self._install_thread.quit)
        self._install_worker.failed.connect(self._install_thread.quit)
        self._install_thread.start()

    def _model_install_done(self, progress: QProgressDialog) -> None:
        progress.close()
        self.status_label.setText("Handwriting model installed and ready for offline use.")

    def _model_install_failed(
        self, progress: QProgressDialog, message: str, details: str
    ) -> None:
        progress.close()
        self._error(
            "The model installation did not finish",
            f"No project data was affected. {message}",
            details,
        )

    def _select_line(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None or not self.project:
            return
        self.save_current_edit()
        self.current_line_id = int(current.data(Qt.UserRole))
        line = next(item for item in self.project.lines(self.current_page) if item.id == self.current_line_id)
        self.editor.blockSignals(True)
        self.editor.setPlainText(line.display_text)
        self.editor.blockSignals(False)
        for overlay in self._overlays:
            selected = overlay.data(0) == line.id
            overlay.setBrush(QBrush(QColor(45, 108, 223, 60) if selected else QColor(0, 0, 0, 0)))

    def _autosave_edit(self) -> None:
        if self.current_line_id is not None and self.project:
            self.project.correct_line(self.current_line_id, self.editor.toPlainText())

    @Slot()
    def save_current_edit(self) -> None:
        self._autosave_edit()

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
    def export_project(self) -> None:
        if not self.project:
            return
        filename, selected = QFileDialog.getSaveFileName(
            self, "Export transcription", "transcription.txt",
            "Text (*.txt);;Word (*.docx);;CSV (*.csv);;JSON (*.json)"
        )
        if not filename:
            return
        try:
            suffix = Path(filename).suffix.lower()
            options = ExportOptions(uncertainty_markers=True)
            {".txt": export_text, ".docx": export_docx}.get(suffix, lambda *_: None)(self.project, filename, options)
            if suffix == ".csv":
                export_csv(self.project, filename)
            elif suffix == ".json":
                export_json(self.project, filename)
            elif suffix not in {".txt", ".docx"}:
                raise ValueError(f"Unsupported export format: {suffix or selected}")
            self.status_label.setText(f"Exported {Path(filename).name}")
        except Exception as error:
            self._error("The export could not be created", str(error))

    def about(self) -> None:
        QMessageBox.about(
            self, "About KurrentScholar",
            f"KurrentScholar 0.1.0.dev0\n\nOffline historical handwriting research assistant.\n\n"
            f"Recognition model: {MODEL_ID}\nRevision: {MODEL_REVISION}\nDOI: 10.57967/hf/0442\n"
            "Model developed by Jonas Widmer and Tobias Hodel with the institutions acknowledged upstream; "
            "KurrentScholar did not develop or train it. MIT-licensed application and model."
        )

    def _error(self, title: str, message: str, details: str = "") -> None:
        dialog = QMessageBox(QMessageBox.Critical, title, message, parent=self)
        if details:
            dialog.setDetailedText(details)
        dialog.exec()

    def closeEvent(self, event) -> None:
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

