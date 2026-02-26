"""
ui/tabs/tab_sync.py - Synchronization Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QCheckBox, QSplitter
)
from PyQt5.QtCore import Qt
from ui.components.widgets import StepRunWidget
from app.project import ProjectManager, StepStatus
import sys
from app.runner import ScriptWorker


class SyncTab(QWidget):
    def __init__(self, pm: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = pm
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Synchronization")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Synchronize camera recordings based on motion signals detected from pose keypoints.")
        desc.setObjectName("sectionDesc")
        outer.addWidget(desc)

        splitter = QSplitter(Qt.Vertical)

        group = QGroupBox("Synchronization Settings")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.approx_time_maxspeed = QDoubleSpinBox()
        self.approx_time_maxspeed.setRange(0.1, 5.0)
        self.approx_time_maxspeed.setValue(0.5)
        self.approx_time_maxspeed.setSingleStep(0.1)
        self.approx_time_maxspeed.setSuffix(" s")
        self.approx_time_maxspeed.setToolTip("Approx. time when motion is fastest (used for sync detection)")
        form.addRow("Peak Motion Time:", self.approx_time_maxspeed)

        self.filter_cutoff = QDoubleSpinBox()
        self.filter_cutoff.setRange(0.5, 30.0)
        self.filter_cutoff.setValue(6.0)
        self.filter_cutoff.setSuffix(" Hz")
        form.addRow("Filter Cutoff:", self.filter_cutoff)

        self.filter_order = QSpinBox()
        self.filter_order.setRange(1, 10)
        self.filter_order.setValue(4)
        form.addRow("Filter Order:", self.filter_order)

        self.display = QCheckBox("Display synchronization plots")
        self.display.setChecked(True)
        form.addRow(self.display)

        splitter.addWidget(group)

        self.run_widget = StepRunWidget("Run Synchronization")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)
        splitter.setSizes([280, 300])

        outer.addWidget(splitter)

    def _run(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded.")
            return

        cfg.sync_approx_time_maxspeed = self.approx_time_maxspeed.value()
        cfg.sync_filter_cutoff = self.filter_cutoff.value()
        cfg.sync_filter_order = self.filter_order.value()
        cfg.sync_display = self.display.isChecked()

        self.run_widget.set_running(True)
        self.run_widget.log.append(f"[INFO] Sync | Peak time: {cfg.sync_approx_time_maxspeed}s | Cutoff: {cfg.sync_filter_cutoff}Hz")

        cmd = [sys.executable, '-c',
               f'import os; os.chdir({repr(cfg.project_dir)}); '
               f'from Pose2Sim import Pose2Sim; Pose2Sim.synchronization()']
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
            self.pm.set_step_status(3, StepStatus.DONE)
