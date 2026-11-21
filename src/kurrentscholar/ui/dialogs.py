from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from kurrentscholar.constants import DOWNLOAD_CATALOG, HELPER_MODEL, ModelSpec
from kurrentscholar.recognition import LocalHelpBackend, ModelManager


class TutorialDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to KurrentScholar")
        self.resize(650, 430)
        self.pages = QStackedWidget()
        content = [
            (
                "Private, offline transcription",
                "KurrentScholar keeps manuscript images, projects, corrections, and exports on this "
                "computer. An internet connection is used only when you explicitly install a model.",
            ),
            (
                "1 · Open a manuscript",
                "Use File > Open Document for PDF or image files. Choose where to save the .ksproj "
                "research project. You can reopen that project later without importing the document again.",
            ),
            (
                "2 · Choose pages and transcribe",
                "Use Transcription for the current page, a range such as 1-5,8, or the full document. "
                "Completed lines appear immediately, so you may navigate and review while processing continues.",
            ),
            (
                "3 · Review responsibly",
                "Confidence labels prioritize review; they are not accuracy guarantees. Correct a line in the "
                "editor and mark it verified only after comparing it with the image. Verified lines become ground truth.",
            ),
            (
                "4 · Models and ground truth",
                "Models > Model Manager shows installed models and disk use. The ground-truth bundle under Review "
                "exports verified line images for reproducible external GPU fine-tuning; it does not silently retrain the app.",
            ),
            (
                "5 · Export and get help",
                "Export TXT, Word, CSV, Excel, or JSON from File > Export. If something goes wrong, use the optional "
                "local Help Assistant or Help > Diagnostic Log. You can replay this tutorial at any time.",
            ),
        ]
        for title, body in content:
            page = QWidget()
            layout = QVBoxLayout(page)
            heading = QLabel(title)
            heading.setObjectName("tutorialHeading")
            heading.setWordWrap(True)
            text = QLabel(body)
            text.setWordWrap(True)
            text.setAlignment(Qt.AlignTop)
            layout.addStretch(1)
            layout.addWidget(heading)
            layout.addWidget(text)
            layout.addStretch(2)
            self.pages.addWidget(page)
        self.back = QPushButton("Back")
        self.next = QPushButton("Next")
        self.skip = QPushButton("Close")
        self.back.clicked.connect(lambda: self._move(-1))
        self.next.clicked.connect(lambda: self._move(1))
        self.skip.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.back)
        buttons.addStretch(1)
        buttons.addWidget(self.skip)
        buttons.addWidget(self.next)
        layout = QVBoxLayout(self)
        layout.addWidget(self.pages)
        layout.addLayout(buttons)
        self._sync()

    def _move(self, delta: int) -> None:
        target = self.pages.currentIndex() + delta
        if target >= self.pages.count():
            self.accept()
            return
        self.pages.setCurrentIndex(max(0, target))
        self._sync()

    def _sync(self) -> None:
        self.back.setEnabled(self.pages.currentIndex() > 0)
        self.next.setText("Start" if self.pages.currentIndex() == self.pages.count() - 1 else "Next")


class GroundTruthDialog(QDialog):
    def __init__(self, page_count: int, current_page: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ground truth for fine-tuning")
        self.resize(610, 330)
        explanation = QLabel(
            "Reference pages must already be transcribed, corrected, and have every line marked verified. "
            "The exported ZIP contains line crops, UTF-8 labels, a manifest, the pinned base model, and the "
            "intended target pages. Reliable TrOCR fine-tuning requires an external CUDA training environment "
            "and held-out validation pages; KurrentScholar does not run an unsafe one-page CPU trainer."
        )
        explanation.setWordWrap(True)
        self.references = QLineEdit(str(current_page))
        self.references.setPlaceholderText(f"e.g. 1-3 (available: 1-{page_count})")
        self.targets = QLineEdit(f"1-{page_count}")
        self.targets.setPlaceholderText("e.g. 4-20,25")
        form = QFormLayout()
        form.addRow("Verified reference pages", self.references)
        form.addRow("Intended target pages", self.targets)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Export training bundle")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(buttons)


class ModelManagerDialog(QDialog):
    install_requested = Signal(object)
    remove_requested = Signal(object)
    select_requested = Signal(object)

    def __init__(self, project_model: ModelSpec | None, parent=None) -> None:
        super().__init__(parent)
        self.project_model = project_model
        self.setWindowTitle("Model Manager")
        self.resize(930, 460)
        intro = QLabel(
            "Models are pinned, integrity-checked, and stored separately from the application. "
            "Removing one frees disk space but never deletes project results."
        )
        intro.setWordWrap(True)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Model", "Purpose", "License", "Download", "Status", "Disk"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for column in (2, 3, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.install = QPushButton("Install / repair")
        self.remove = QPushButton("Remove")
        self.select = QPushButton("Use for open project")
        close = QPushButton("Close")
        self.install.clicked.connect(lambda: self._emit(self.install_requested))
        self.remove.clicked.connect(lambda: self._emit(self.remove_requested))
        self.select.clicked.connect(lambda: self._emit(self.select_requested))
        close.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.install)
        buttons.addWidget(self.remove)
        buttons.addWidget(self.select)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.refresh()

    def refresh(self) -> None:
        selected_key = self.selected_spec().key if self.selected_spec() else None
        self.table.setRowCount(0)
        for spec in DOWNLOAD_CATALOG:
            row = self.table.rowCount()
            self.table.insertRow(row)
            manager = ModelManager(spec=spec)
            status = manager.status()
            downloaded = manager.downloaded_bytes()
            state = "Installed" if status.installed else (
                "Needs repair" if downloaded else "Not installed"
            )
            if self.project_model == spec:
                state += " · project"
            values = [
                spec.display_name,
                spec.summary,
                spec.license,
                f"{spec.required_bytes / (1024 ** 3):.2f} GiB",
                state,
                f"{downloaded / (1024 ** 3):.2f} GiB",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, spec.key)
                self.table.setItem(row, column, item)
            if spec.key == selected_key:
                self.table.selectRow(row)
        if self.table.rowCount() and not self.table.selectedItems():
            self.table.selectRow(0)
        self._sync_buttons()

    def selected_spec(self) -> ModelSpec | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        key = self.table.item(row, 0).data(Qt.UserRole)
        return next((spec for spec in DOWNLOAD_CATALOG if spec.key == key), None)

    def _emit(self, signal: Signal) -> None:
        spec = self.selected_spec()
        if spec:
            signal.emit(spec)

    def _sync_buttons(self) -> None:
        spec = self.selected_spec()
        manager = ModelManager(spec=spec) if spec else None
        status = manager.status() if manager else None
        self.install.setEnabled(bool(spec and not status.installed))
        self.remove.setEnabled(bool(spec and manager.downloaded_bytes()))
        self.select.setEnabled(bool(
            spec and spec.kind == "recognition" and status.installed and self.project_model is not None
        ))


class HelpWorker(QObject):
    answered = Signal(str)
    failed = Signal(str)

    def __init__(self, backend: LocalHelpBackend, question: str) -> None:
        super().__init__()
        self.backend = backend
        self.question = question

    @Slot()
    def run(self) -> None:
        try:
            self.answered.emit(self.backend.answer(self.question))
        except Exception as error:
            self.failed.emit(str(error))


class LocalHelpDialog(QDialog):
    install_requested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Local Help Assistant")
        self.resize(650, 520)
        notice = QLabel(
            "Optional and fully local after installation. It is intended only for navigation and troubleshooting, "
            "is English-oriented, and may be wrong. Do not paste manuscript text; the assistant does not need it."
        )
        notice.setWordWrap(True)
        self.question = QTextEdit()
        self.question.setPlaceholderText("For example: How do I transcribe only pages 5 to 12?")
        self.question.setMaximumHeight(100)
        self.response = QTextBrowser()
        self.response.setPlaceholderText("The answer will appear here.")
        self.ask = QPushButton("Ask locally")
        self.install = QPushButton("Install helper model")
        close = QPushButton("Close")
        self.ask.clicked.connect(self._ask)
        self.install.clicked.connect(lambda: self.install_requested.emit(HELPER_MODEL))
        close.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.ask)
        buttons.addWidget(self.install)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(notice)
        layout.addWidget(self.question)
        layout.addWidget(self.response, 1)
        layout.addLayout(buttons)
        self._thread: QThread | None = None
        self._worker: HelpWorker | None = None
        self._backend: LocalHelpBackend | None = None
        self.refresh()

    def refresh(self) -> None:
        installed = ModelManager(spec=HELPER_MODEL).status().installed
        self.ask.setEnabled(installed and self._thread is None)
        self.install.setVisible(not installed)

    def _ask(self) -> None:
        manager = ModelManager(spec=HELPER_MODEL)
        if not manager.status().installed or self._thread is not None:
            return
        question = self.question.toPlainText().strip()
        if not question:
            self.response.setText("Enter a question first.")
            return
        self.response.setText("Thinking locally…")
        self.ask.setEnabled(False)
        self._thread = QThread(self)
        if self._backend is None:
            self._backend = LocalHelpBackend(manager.root)
        self._worker = HelpWorker(self._backend, question)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.answered.connect(self._finished)
        self._worker.failed.connect(lambda message: self._finished(f"The helper failed: {message}"))
        self._worker.answered.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.answered.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()

    @Slot(str)
    def _finished(self, message: str) -> None:
        self.response.setPlainText(message)

    @Slot()
    def _thread_finished(self) -> None:
        if self._thread:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.refresh()

    def reject(self) -> None:
        if self._thread is None:
            super().reject()

    @property
    def busy(self) -> bool:
        return self._thread is not None
