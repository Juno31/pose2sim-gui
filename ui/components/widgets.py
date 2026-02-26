"""
ui/widgets.py - Reusable widgets
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QTextCursor


class PathPicker(QWidget):
    """A line edit + browse button for picking files or directories."""
    path_changed = pyqtSignal(str)

    def __init__(self, label: str = "", mode: str = "dir", filter: str = "", placeholder: str = "", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.filter = filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if label:
            lbl = QLabel(label)
            lbl.setMinimumWidth(160)
            layout.addWidget(lbl)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder or ("Select folder..." if mode == "dir" else "Select file..."))
        self.line_edit.textChanged.connect(self.path_changed.emit)
        layout.addWidget(self.line_edit)

        btn = QPushButton("Browse")
        btn.setObjectName("browseBtn")
        btn.setFixedWidth(80)
        btn.clicked.connect(self._browse)
        layout.addWidget(btn)

    def _browse(self):
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
        elif self.mode == "file":
            path, _ = QFileDialog.getOpenFileName(self, "Select File", filter=self.filter)
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Save File", filter=self.filter)

        if path:
            self.line_edit.setText(path)

    def path(self) -> str:
        return self.line_edit.text()

    def set_path(self, path: str):
        self.line_edit.setText(path)


class LogWidget(QWidget):
    """Log output widget with colored messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        lbl = QLabel("Console Output")
        lbl.setStyleSheet("color: #8b949e; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;")
        header.addWidget(lbl)
        header.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(60, 24)
        clear_btn.clicked.connect(self.clear)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        self.text = QTextEdit()
        self.text.setObjectName("logOutput")
        self.text.setReadOnly(True)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.text)

    def append(self, msg: str):
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Color by prefix
        if "[ERROR]" in msg:
            color = "#f85149"
        elif "[SUCCESS]" in msg:
            color = "#7ee787"
        elif "[WARNING]" in msg:
            color = "#e3b341"
        elif "[INFO]" in msg:
            color = "#58a6ff"
        else:
            color = "#c9d1d9"

        cursor.insertHtml(f'<span style="color:{color}; font-family:Consolas; font-size:12px;">{msg}</span><br>')
        self.text.setTextCursor(cursor)
        self.text.ensureCursorVisible()

    def clear(self):
        self.text.clear()


class StepRunWidget(QWidget):
    """Bottom panel with Run button, progress bar, and log."""
    run_requested = pyqtSignal()
    abort_requested = pyqtSignal()

    def __init__(self, run_label: str = "Run Step", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Run controls row
        ctrl = QHBoxLayout()
        self.run_btn = QPushButton(run_label)
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.setFixedHeight(36)
        self.run_btn.clicked.connect(self.run_requested.emit)
        ctrl.addWidget(self.run_btn)

        self.abort_btn = QPushButton("Abort")
        self.abort_btn.setObjectName("dangerBtn")
        self.abort_btn.setFixedHeight(36)
        self.abort_btn.setEnabled(False)
        self.abort_btn.clicked.connect(self.abort_requested.emit)
        ctrl.addWidget(self.abort_btn)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        ctrl.addWidget(self.status_label)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)

        # Log
        self.log = LogWidget()
        layout.addWidget(self.log)

    def set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.abort_btn.setEnabled(running)
        if running:
            self.status_label.setText("Running...")
            self.status_label.setStyleSheet("color: #e3b341; font-size: 12px;")
            self.progress.setValue(0)
        else:
            self.status_label.setStyleSheet("color: #8b949e; font-size: 12px;")

    def set_done(self, success: bool, msg: str = ""):
        self.set_running(False)
        if success:
            self.status_label.setText("✓ Done")
            self.status_label.setStyleSheet("color: #7ee787; font-size: 12px;")
            self.progress.setValue(100)
        else:
            self.status_label.setText(f"✗ Failed: {msg[:60]}")
            self.status_label.setStyleSheet("color: #f85149; font-size: 12px;")

    def log_message(self, msg: str):
        self.log.append(msg)

    def set_progress(self, val: int):
        self.progress.setValue(val)
