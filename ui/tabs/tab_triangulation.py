"""
ui/tabs/tab_triangulation.py - Triangulation Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QCheckBox, QSplitter, QComboBox, QPushButton,
    QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from ui.components.widgets import StepRunWidget
from app.project import ProjectManager, StepStatus
import sys
from app.runner import ScriptWorker


class TriangulationTab(QWidget):
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

        title = QLabel("Triangulation")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Reconstruct 3D marker positions from 2D pose estimates using direct linear transformation (DLT).")
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

        group = QGroupBox("Triangulation Settings")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.reproj_error = QDoubleSpinBox()
        self.reproj_error.setRange(1.0, 100.0)
        self.reproj_error.setValue(15.0)
        self.reproj_error.setSuffix(" px")
        self.reproj_error.setToolTip("Max reprojection error. Points above this threshold are excluded.")
        form.addRow("Reproj. Error Threshold:", self.reproj_error)

        self.likelihood_threshold = QDoubleSpinBox()
        self.likelihood_threshold.setRange(0.0, 1.0)
        self.likelihood_threshold.setSingleStep(0.05)
        self.likelihood_threshold.setValue(0.3)
        self.likelihood_threshold.setToolTip("Keypoints with likelihood below this are ignored")
        form.addRow("Likelihood Threshold:", self.likelihood_threshold)

        self.min_cameras = QSpinBox()
        self.min_cameras.setRange(2, 8)
        self.min_cameras.setValue(2)
        self.min_cameras.setToolTip("Minimum cameras needed to triangulate a point")
        form.addRow("Min Cameras:", self.min_cameras)

        self.interpolation = QComboBox()
        self.interpolation.addItems(["linear", "slinear", "quadratic", "cubic", "none"])
        self.interpolation.setToolTip("Interpolation method for missing points")
        form.addRow("Interpolation:", self.interpolation)

        self.interp_gap = QSpinBox()
        self.interp_gap.setRange(1, 200)
        self.interp_gap.setValue(20)
        self.interp_gap.setSuffix(" frames")
        self.interp_gap.setToolTip("Only interpolate gaps smaller than this many frames")
        form.addRow("Max Gap to Interpolate:", self.interp_gap)

        self.show_reproj = QCheckBox("Show reprojection error plot")
        form.addRow(self.show_reproj)

        self.make_c3d = QCheckBox("Also save as .c3d")
        self.make_c3d.setChecked(True)
        form.addRow(self.make_c3d)

        self.remove_incomplete = QCheckBox("Remove frames where any keypoint is missing")
        self.remove_incomplete.setToolTip("If true, a frame is dropped if any keypoint can't be triangulated")
        form.addRow(self.remove_incomplete)

        self.sections_to_keep = QComboBox()
        self.sections_to_keep.addItems(["all", "largest", "first", "last"])
        self.sections_to_keep.setToolTip("Which valid continuous sections to keep after triangulation")
        form.addRow("Sections to Keep:", self.sections_to_keep)

        self.fill_large_gaps = QComboBox()
        self.fill_large_gaps.addItems(["last_value", "nan", "zeros"])
        self.fill_large_gaps.setToolTip("How to fill gaps larger than the interpolation threshold")
        form.addRow("Fill Large Gaps:", self.fill_large_gaps)

        self.max_distance_m = QDoubleSpinBox()
        self.max_distance_m.setRange(0.1, 10.0)
        self.max_distance_m.setSingleStep(0.1)
        self.max_distance_m.setValue(1.0)
        self.max_distance_m.setSuffix(" m")
        self.max_distance_m.setToolTip("Max movement per frame before treating as a new person")
        form.addRow("Max Distance:", self.max_distance_m)

        splitter.addWidget(group)

        self.run_widget = StepRunWidget("Run Triangulation")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)
        splitter.setSizes([320, 300])

        outer.addWidget(splitter)

    def load_from_toml(self, data: dict):
        """Populate widgets from a parsed Config.toml dict."""
        tri = data.get("triangulation", {})

        val = tri.get("reproj_error_threshold_triangulation")
        if isinstance(val, (int, float)):
            self.reproj_error.setValue(float(val))

        val = tri.get("likelihood_threshold_triangulation")
        if isinstance(val, (int, float)):
            self.likelihood_threshold.setValue(float(val))

        val = tri.get("min_cameras_for_triangulation")
        if isinstance(val, int):
            self.min_cameras.setValue(val)

        val = tri.get("interpolation")
        if isinstance(val, str):
            idx = self.interpolation.findText(val)
            if idx >= 0:
                self.interpolation.setCurrentIndex(idx)

        val = tri.get("interp_if_gap_smaller_than")
        if isinstance(val, int):
            self.interp_gap.setValue(val)

        val = tri.get("make_c3d")
        if isinstance(val, bool):
            self.make_c3d.setChecked(val)

        val = tri.get("remove_incomplete_frames")
        if isinstance(val, bool):
            self.remove_incomplete.setChecked(val)

        val = tri.get("sections_to_keep")
        if isinstance(val, str):
            idx = self.sections_to_keep.findText(val)
            if idx >= 0:
                self.sections_to_keep.setCurrentIndex(idx)

        val = tri.get("fill_large_gaps_with")
        if isinstance(val, str):
            idx = self.fill_large_gaps.findText(val)
            if idx >= 0:
                self.fill_large_gaps.setCurrentIndex(idx)

        val = tri.get("max_distance_m")
        if isinstance(val, (int, float)):
            self.max_distance_m.setValue(float(val))

    def _save_config(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.save_status.setText("✗ No project loaded")
            self.save_status.setStyleSheet("color: #f85149; font-size: 11px;")
            return
        from app.toml_bridge import save_toml_values
        save_toml_values(cfg.project_dir, [
            ("triangulation", "reproj_error_threshold_triangulation", self.reproj_error.value()),
            ("triangulation", "likelihood_threshold_triangulation",   self.likelihood_threshold.value()),
            ("triangulation", "min_cameras_for_triangulation",        self.min_cameras.value()),
            ("triangulation", "interpolation",                        self.interpolation.currentText()),
            ("triangulation", "interp_if_gap_smaller_than",           self.interp_gap.value()),
            ("triangulation", "make_c3d",                             self.make_c3d.isChecked()),
            ("triangulation", "remove_incomplete_frames",             self.remove_incomplete.isChecked()),
            ("triangulation", "sections_to_keep",                     self.sections_to_keep.currentText()),
            ("triangulation", "fill_large_gaps_with",                 self.fill_large_gaps.currentText()),
            ("triangulation", "max_distance_m",                       self.max_distance_m.value()),
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

        cfg.triang_reproj_error_threshold = self.reproj_error.value()
        cfg.triang_min_cameras = self.min_cameras.value()
        cfg.triang_interpolate_missing = self.interpolation.currentText() != "none"
        cfg.triang_interp_if_gap_smaller_than = self.interp_gap.value()
        cfg.triang_show_reprojection = self.show_reproj.isChecked()

        self.run_widget.set_running(True)
        self.run_widget.log.append(
            f"[INFO] Triangulation | Reproj threshold: {cfg.triang_reproj_error_threshold}px | "
            f"Min cams: {cfg.triang_min_cameras}"
        )

        cmd = [sys.executable, '-c',
               f'import os; os.chdir({repr(cfg.project_dir)}); '
               f'from Pose2Sim import Pose2Sim; Pose2Sim.triangulation()']
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
            self.pm.set_step_status(4, StepStatus.DONE)
