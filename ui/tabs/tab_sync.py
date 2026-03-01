"""
ui/tabs/tab_sync.py - Synchronization Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QCheckBox, QSplitter, QPushButton, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
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
        pm.register_change_callback(self._on_project_changed)

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

        # Save Config row
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("💾  Save Config")
        self.save_btn.setToolTip("Write current settings to Config.toml")
        self.save_btn.clicked.connect(self._save_config)
        save_row.addWidget(self.save_btn)
        self.save_status = QLabel("")
        self.save_status.setStyleSheet("color: #7ee787; font-size: 11px;")
        save_row.addWidget(self.save_status)
        save_row.addStretch()
        outer.addLayout(save_row)

        splitter = QSplitter(Qt.Vertical)

        group = QGroupBox("Synchronization Settings")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.approx_time_maxspeed = QDoubleSpinBox()
        self.approx_time_maxspeed.setRange(0.1, 5.0)
        self.approx_time_maxspeed.setValue(0.5)
        self.approx_time_maxspeed.setSingleStep(0.1)
        self.approx_time_maxspeed.setSuffix(" s")
        self.approx_time_maxspeed.setToolTip("Approx. time when motion is fastest (used for sync detection). Set to 0.5 if 'auto'.")
        form.addRow("Peak Motion Time:", self.approx_time_maxspeed)

        self.time_range = QDoubleSpinBox()
        self.time_range.setRange(0.5, 10.0)
        self.time_range.setValue(2.0)
        self.time_range.setSuffix(" s")
        self.time_range.setToolTip("Search range around peak motion time")
        form.addRow("Search Range:", self.time_range)

        self.filter_cutoff = QDoubleSpinBox()
        self.filter_cutoff.setRange(0.5, 30.0)
        self.filter_cutoff.setValue(6.0)
        self.filter_cutoff.setSuffix(" Hz")
        form.addRow("Filter Cutoff:", self.filter_cutoff)

        self.filter_order = QSpinBox()
        self.filter_order.setRange(1, 10)
        self.filter_order.setValue(4)
        form.addRow("Filter Order:", self.filter_order)

        self.likelihood_threshold = QDoubleSpinBox()
        self.likelihood_threshold.setRange(0.0, 1.0)
        self.likelihood_threshold.setSingleStep(0.05)
        self.likelihood_threshold.setValue(0.4)
        self.likelihood_threshold.setToolTip("Keypoints below this likelihood are ignored")
        form.addRow("Likelihood Threshold:", self.likelihood_threshold)

        self.display = QCheckBox("Display synchronization plots")
        self.display.setChecked(True)
        form.addRow(self.display)

        self.save_sync_plots = QCheckBox("Save synchronization plots")
        self.save_sync_plots.setChecked(True)
        form.addRow(self.save_sync_plots)

        self.sync_gui = QCheckBox("Use interactive sync GUI (popup player)")
        self.sync_gui.setChecked(True)
        self.sync_gui.setToolTip("If checked, a player pops up for manual sync parameter entry")
        form.addRow(self.sync_gui)

        self.keypoints_to_consider = QLineEdit("all")
        self.keypoints_to_consider.setPlaceholderText("all  or  ['RWrist', 'RElbow']")
        self.keypoints_to_consider.setToolTip(
            "'all' or a list of keypoint names with sharp vertical motion, e.g. ['RWrist']"
        )
        form.addRow("Keypoints:", self.keypoints_to_consider)

        splitter.addWidget(group)

        self.run_widget = StepRunWidget("Run Synchronization")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)
        splitter.setSizes([280, 300])

        outer.addWidget(splitter)

    def load_from_toml(self, data: dict):
        """Populate widgets from a parsed Config.toml dict."""
        sync = data.get("synchronization", {})

        val = sync.get("approx_time_maxspeed")
        if isinstance(val, (int, float)):
            self.approx_time_maxspeed.setValue(float(val))

        val = sync.get("time_range_around_maxspeed")
        if isinstance(val, (int, float)):
            self.time_range.setValue(float(val))

        val = sync.get("filter_cutoff")
        if isinstance(val, (int, float)):
            self.filter_cutoff.setValue(float(val))

        val = sync.get("filter_order")
        if isinstance(val, int):
            self.filter_order.setValue(val)

        val = sync.get("likelihood_threshold")
        if isinstance(val, (int, float)):
            self.likelihood_threshold.setValue(float(val))

        val = sync.get("display_sync_plots")
        if isinstance(val, bool):
            self.display.setChecked(val)

        val = sync.get("save_sync_plots")
        if isinstance(val, bool):
            self.save_sync_plots.setChecked(val)

        val = sync.get("synchronization_gui")
        if isinstance(val, bool):
            self.sync_gui.setChecked(val)

        val = sync.get("keypoints_to_consider")
        if val is not None:
            self.keypoints_to_consider.setText(str(val))

    def _save_config(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.save_status.setText("✗ No project loaded")
            self.save_status.setStyleSheet("color: #f85149; font-size: 11px;")
            return
        from app.toml_bridge import save_toml_values
        save_toml_values(cfg.project_dir, [
            ("synchronization", "approx_time_maxspeed",        self.approx_time_maxspeed.value()),
            ("synchronization", "time_range_around_maxspeed",  self.time_range.value()),
            ("synchronization", "filter_cutoff",               self.filter_cutoff.value()),
            ("synchronization", "filter_order",                self.filter_order.value()),
            ("synchronization", "likelihood_threshold",        self.likelihood_threshold.value()),
            ("synchronization", "display_sync_plots",          self.display.isChecked()),
            ("synchronization", "save_sync_plots",             self.save_sync_plots.isChecked()),
            ("synchronization", "synchronization_gui",         self.sync_gui.isChecked()),
            ("synchronization", "keypoints_to_consider",       self.keypoints_to_consider.text().strip()),
        ])
        self.save_status.setText("✓ Config saved")
        self.save_status.setStyleSheet("color: #7ee787; font-size: 11px;")
        QTimer.singleShot(3000, lambda: self.save_status.setText(""))

    def _on_project_changed(self, cfg):
        if cfg.project_dir:
            from app.toml_bridge import load_toml
            data = load_toml(cfg.project_dir)
            if data:
                self.load_from_toml(data)

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
        self.run_widget.log.append(
            f"[INFO] Sync | Peak time: {cfg.sync_approx_time_maxspeed}s | "
            f"Cutoff: {cfg.sync_filter_cutoff}Hz"
        )

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
