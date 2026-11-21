from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kurrentscholar.constants import DOWNLOAD_CATALOG, HELPER_MODEL, ModelSpec
from kurrentscholar.recognition import LocalHelpBackend, ModelManager


class TutorialOverlay(QWidget):
    """A lightweight coach-mark tour anchored to the real application controls."""

    finished = Signal()

    def __init__(self, steps: list[tuple[str, str, QWidget | None]], parent: QWidget) -> None:
        super().__init__(parent)
        self.steps = steps
        self.index = 0
        self.setObjectName("tutorialOverlay")
        self.setFocusPolicy(Qt.StrongFocus)

        self.card = QFrame(self)
        self.card.setObjectName("tutorialCard")
        self.card.setMinimumWidth(390)
        self.card.setMaximumWidth(470)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 22, 24, 20)
        self.kicker = QLabel("WELCOME")
        self.kicker.setObjectName("tutorialKicker")
        self.heading = QLabel()
        self.heading.setObjectName("tutorialHeading")
        self.heading.setWordWrap(True)
        self.body = QLabel()
        self.body.setObjectName("tutorialBody")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.PlainText)
        self.progress = QLabel()
        self.progress.setObjectName("tutorialProgress")
        self.back = QPushButton("Back")
        self.next = QPushButton("Next")
        self.skip = QPushButton("Skip tour")
        self.back.clicked.connect(lambda: self._move(-1))
        self.next.clicked.connect(lambda: self._move(1))
        self.skip.clicked.connect(self.close_tour)
        buttons = QHBoxLayout()
        buttons.addWidget(self.progress)
        buttons.addStretch(1)
        buttons.addWidget(self.back)
        buttons.addWidget(self.next)
        card_layout.addWidget(self.kicker)
        card_layout.addWidget(self.heading)
        card_layout.addWidget(self.body)
        card_layout.addSpacing(8)
        card_layout.addLayout(buttons)
        card_layout.addWidget(self.skip, alignment=Qt.AlignRight)
        self._sync()

    def showEvent(self, event) -> None:
        parent = self.parentWidget()
        if parent:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())
        self.raise_()
        self.setFocus()
        self._position_card()
        super().showEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Move):
            self.setGeometry(self.parentWidget().rect())
            self._position_card()
        return super().eventFilter(watched, event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        target = self._target_rect()
        if target:
            cutout = QPainterPath()
            cutout.addRoundedRect(QRectF(target), 12, 12)
            shade = shade.subtracted(cutout)
        painter.fillPath(shade, QColor(26, 32, 39, 174))
        if target:
            painter.setPen(QPen(QColor("#B89491"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(target, 12, 12)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close_tour()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Right):
            self._move(1)
        elif event.key() == Qt.Key_Left:
            self._move(-1)
        else:
            super().keyPressEvent(event)

    def _target_rect(self) -> QRect | None:
        target = self.steps[self.index][2]
        if target is None or not target.isVisible():
            return None
        top_left = self.mapFromGlobal(target.mapToGlobal(QPoint(0, 0)))
        return QRect(top_left, target.size()).adjusted(-8, -8, 8, 8)

    def _position_card(self) -> None:
        self.card.adjustSize()
        size = self.card.sizeHint()
        width = min(max(size.width(), 390), min(470, max(390, self.width() - 40)))
        self.card.setFixedWidth(width)
        self.card.adjustSize()
        card_size = self.card.sizeHint()
        margin = 24
        target = self._target_rect()
        if target is None:
            x = max(margin, (self.width() - card_size.width()) // 2)
            y = max(margin, (self.height() - card_size.height()) // 2)
        else:
            spaces = {
                "left": target.left() - margin,
                "right": self.width() - target.right() - margin,
                "top": target.top() - margin,
                "bottom": self.height() - target.bottom() - margin,
            }
            side = max(spaces, key=spaces.get)
            if side == "left":
                x = target.left() - card_size.width() - margin
                y = target.center().y() - card_size.height() // 2
            elif side == "right":
                x = target.right() + margin
                y = target.center().y() - card_size.height() // 2
            elif side == "top":
                x = target.center().x() - card_size.width() // 2
                y = target.top() - card_size.height() - margin
            else:
                x = target.center().x() - card_size.width() // 2
                y = target.bottom() + margin
            x = min(max(margin, x), max(margin, self.width() - card_size.width() - margin))
            y = min(max(margin, y), max(margin, self.height() - card_size.height() - margin))
        self.card.move(x, y)
        self.card.raise_()

    def _move(self, delta: int) -> None:
        target = self.index + delta
        if target >= len(self.steps):
            self.close_tour()
            return
        self.index = max(0, target)
        self._sync()

    def _sync(self) -> None:
        title, body, target = self.steps[self.index]
        self.kicker.setText("WELCOME" if self.index == 0 else "QUICK TOUR")
        self.heading.setText(title)
        self.body.setText(body)
        self.progress.setText(f"{self.index + 1} of {len(self.steps)}")
        self.back.setEnabled(self.index > 0)
        self.next.setText("Start using KurrentScholar" if self.index == len(self.steps) - 1 else "Next")
        self.skip.setVisible(self.index < len(self.steps) - 1)
        self._position_card()
        self.update()

    def close_tour(self) -> None:
        parent = self.parentWidget()
        if parent:
            parent.removeEventFilter(self)
        self.hide()
        self.finished.emit()
        self.deleteLater()


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


class LocalHelpPanel(QWidget):
    install_requested = Signal(object)
    close_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("helperPanel")
        self.setMinimumWidth(350)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._message_labels: list[QLabel] = []
        self._thinking: QLabel | None = None

        avatar = QLabel("?")
        avatar.setObjectName("helperAvatar")
        avatar.setAlignment(Qt.AlignCenter)
        title = QLabel("KurrentBot")
        title.setObjectName("helperTitle")
        subtitle = QLabel("Local guide to KurrentScholar")
        subtitle.setObjectName("helperSubtitle")
        identity = QVBoxLayout()
        identity.setSpacing(0)
        identity.addWidget(title)
        identity.addWidget(subtitle)
        reset = QPushButton("↻")
        reset.setObjectName("helperHeaderButton")
        reset.setToolTip("Start a new conversation")
        close = QPushButton("×")
        close.setObjectName("helperHeaderButton")
        close.setToolTip("Close KurrentBot")
        reset.clicked.connect(self.reset_conversation)
        close.clicked.connect(self.close_requested)
        header = QHBoxLayout()
        header.addWidget(avatar)
        header.addLayout(identity)
        header.addStretch(1)
        header.addWidget(reset)
        header.addWidget(close)

        notice = QLabel(
            "Optional and fully local after installation. Ask about navigation and troubleshooting; "
            "do not paste manuscript text."
        )
        notice.setObjectName("helperNotice")
        notice.setWordWrap(True)

        self.message_area = QScrollArea()
        self.message_area.setObjectName("helperMessages")
        self.message_area.setWidgetResizable(True)
        self.message_area.setFrameShape(QFrame.NoFrame)
        message_host = QWidget()
        message_host.setObjectName("helperMessageHost")
        self.messages = QVBoxLayout(message_host)
        self.messages.setContentsMargins(10, 12, 10, 12)
        self.messages.setSpacing(10)
        self.messages.setAlignment(Qt.AlignTop)
        self.message_area.setWidget(message_host)

        self.question = QLineEdit()
        self.question.setObjectName("helperInput")
        self.question.setPlaceholderText("Ask how to use KurrentScholar…")
        self.question.setMaxLength(400)
        self.question.returnPressed.connect(self._ask)
        self.ask = QPushButton("Send")
        self.ask.setObjectName("helperSend")
        self.install = QPushButton("Install helper model")
        self.install.setObjectName("helperInstall")
        self.ask.clicked.connect(self._ask)
        self.install.clicked.connect(lambda: self.install_requested.emit(HELPER_MODEL))
        input_row = QHBoxLayout()
        input_row.addWidget(self.question, 1)
        input_row.addWidget(self.ask)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addLayout(header)
        layout.addWidget(notice)
        layout.addWidget(self.message_area, 1)
        layout.addWidget(self.install)
        layout.addLayout(input_row)
        self._thread: QThread | None = None
        self._worker: HelpWorker | None = None
        self._backend: LocalHelpBackend | None = None
        self.reset_conversation()
        self.refresh()

    def refresh(self) -> None:
        installed = ModelManager(spec=HELPER_MODEL).status().installed
        self.ask.setEnabled(installed and self._thread is None)
        self.question.setEnabled(installed and self._thread is None)
        self.install.setVisible(not installed)

    def _ask(self) -> None:
        manager = ModelManager(spec=HELPER_MODEL)
        if not manager.status().installed or self._thread is not None:
            return
        question = self.question.text().strip()
        if not question:
            self.question.setFocus()
            return
        self._add_message(question, user=True)
        self.question.clear()
        self._thinking = self._add_message("Thinking locally…", user=False)
        self.ask.setEnabled(False)
        self.question.setEnabled(False)
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
        if self._thinking:
            self._thinking.setText(message)
            self._thinking = None
        else:
            self._add_message(message, user=False)
        QTimer.singleShot(0, self._scroll_to_bottom)

    @Slot()
    def _thread_finished(self) -> None:
        if self._thread:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.refresh()

    def reset_conversation(self) -> None:
        if self._thread is not None:
            return
        while self.messages.count():
            item = self.messages.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._message_labels.clear()
        self._add_message(
            "Hi, I’m KurrentBot — your local guide to KurrentScholar. Ask me how to open a "
            "project, transcribe selected pages, review uncertain lines, manage models, or export results.",
            user=False,
        )

    def _add_message(self, text: str, *, user: bool) -> QLabel:
        label = QLabel(text)
        label.setObjectName("helperUserMessage" if user else "helperBotMessage")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        label.setMaximumWidth(300)
        row = QHBoxLayout()
        if user:
            row.addStretch(1)
            row.addWidget(label)
        else:
            row.addWidget(label)
            row.addStretch(1)
        holder = QWidget()
        holder.setObjectName("helperMessageRow")
        holder.setLayout(row)
        self.messages.addWidget(holder)
        self._message_labels.append(label)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return label

    def _scroll_to_bottom(self) -> None:
        bar = self.message_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    @property
    def busy(self) -> bool:
        return self._thread is not None
