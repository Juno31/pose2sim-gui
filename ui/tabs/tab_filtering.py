"""
ui/tabs/tab_filtering.py - Filtering Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QCheckBox, QSplitter, QComboBox
)
from PyQt5.QtCore import Qt
from ui.components.widgets import StepRunWidget
from app.project import ProjectManager, StepStatus
import sys
from app.runner import ScriptWorker


class FilteringTab(QWidget):
    def __init__(self, pm: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = pm
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Filtering")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Smooth 3D trajectories to remove noise and artifacts from triangulation.")
        desc.setObjectName("sectionDesc")
        outer.addWidget(desc)

        splitter = QSplitter(Qt.Vertical)

        group = QGroupBox("Filter Settings")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.filter_type = QComboBox()
        self.filter_type.addItems(["butterworth", "kalman", "gaussian", "LOESS", "median"])
        self.filter_type.currentTextChanged.connect(self._on_filter_changed)
        form.addRow("Filter Type:", self.filter_type)

        # Filter info label
        self.filter_info = QLabel()
        self.filter_info.setStyleSheet("color: #8b949e; font-size: 11px;")
        self.filter_info.setWordWrap(True)
        form.addRow(self.filter_info)

        self.cutoff_freq = QDoubleSpinBox()
        self.cutoff_freq.setRange(0.5, 50.0)
        self.cutoff_freq.setValue(6.0)
        self.cutoff_freq.setSuffix(" Hz")
        form.addRow("Cutoff Frequency:", self.cutoff_freq)

        self.filter_order = QSpinBox()
        self.filter_order.setRange(1, 10)
        self.filter_order.setValue(4)
        form.addRow("Filter Order:", self.filter_order)

        self.display = QCheckBox("Display filter results")
        form.addRow(self.display)

        self._on_filter_changed("butterworth")
        splitter.addWidget(group)

        self.run_widget = StepRunWidget("Run Filtering")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)
        splitter.setSizes([300, 300])

        outer.addWidget(splitter)

    def _on_filter_changed(self, filter_type):
        descriptions = {
            "butterworth": "Classic low-pass filter. Best for smooth continuous motion.",
            "kalman": "Optimal for noisy data with known dynamics. Good for sports.",
            "gaussian": "Gaussian kernel smoothing. Adjustable sigma via cutoff.",
            "LOESS": "Local regression. Very smooth but computationally heavy.",
            "median": "Removes spike outliers. Good for removing sudden jumps.",
        }
        self.filter_info.setText(descriptions.get(filter_type, ""))
        needs_cutoff = filter_type in ("butterworth", "kalman", "gaussian")
        needs_order = filter_type in ("butterworth", "kalman")
        self.cutoff_freq.setEnabled(needs_cutoff)
        self.filter_order.setEnabled(needs_order)

    def _run(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded.")
            return

        cfg.filter_type = self.filter_type.currentText()
        cfg.filter_cutoff = self.cutoff_freq.value()
        cfg.filter_order = self.filter_order.value()
        cfg.filter_display = self.display.isChecked()

        self.run_widget.set_running(True)
        self.run_widget.log.append(f"[INFO] Filter: {cfg.filter_type} | Cutoff: {cfg.filter_cutoff}Hz | Order: {cfg.filter_order}")

        cmd = [sys.executable, '-c',
               f'import os; os.chdir({repr(cfg.project_dir)}); '
               f'from Pose2Sim import Pose2Sim; Pose2Sim.filtering()']
        self.worker = ScriptWorker(cmd, cwd=cfg.project_dir)
        self.worker.log_signal.connect(self.run_widget.log_message)
        self.worker.progress_signal.connect(self.run_widget.set_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _abort(self):
        if self.worker:
            self.worker.abort()
        self.run_widget.set_running(False)
        self.run_widget.log.append("[WARNING] Aborted.")

    def _on_finished(self, success, msg):
        self.run_widget.set_done(success, msg)
        if success:
            self.pm.set_step_status(5, StepStatus.DONE)
