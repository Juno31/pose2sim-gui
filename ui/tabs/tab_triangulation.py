"""
ui/tabs/tab_triangulation.py - Triangulation Tab
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QCheckBox, QSplitter
)
from PyQt5.QtCore import Qt
from ui.components.widgets import StepRunWidget
from app.project import ProjectManager, StepStatus
from app.runner import PipelineWorker


class TriangulationTab(QWidget):
    def __init__(self, pm: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = pm
        self.worker = None
        self._build_ui()

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

        self.min_cameras = QSpinBox()
        self.min_cameras.setRange(2, 4)
        self.min_cameras.setValue(2)
        self.min_cameras.setToolTip("Minimum cameras needed to triangulate a point")
        form.addRow("Min Cameras:", self.min_cameras)

        self.interpolate = QCheckBox("Interpolate missing points")
        self.interpolate.setChecked(True)
        form.addRow(self.interpolate)

        self.interp_gap = QSpinBox()
        self.interp_gap.setRange(1, 100)
        self.interp_gap.setValue(10)
        self.interp_gap.setSuffix(" frames")
        self.interp_gap.setToolTip("Only interpolate gaps smaller than this")
        form.addRow("Max Gap to Interpolate:", self.interp_gap)

        self.show_reproj = QCheckBox("Show reprojection error plot")
        form.addRow(self.show_reproj)

        splitter.addWidget(group)

        self.run_widget = StepRunWidget("Run Triangulation")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)
        splitter.setSizes([320, 300])

        outer.addWidget(splitter)

    def _run(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded.")
            return

        cfg.triang_reproj_error_threshold = self.reproj_error.value()
        cfg.triang_min_cameras = self.min_cameras.value()
        cfg.triang_interpolate_missing = self.interpolate.isChecked()
        cfg.triang_interp_if_gap_smaller_than = self.interp_gap.value()
        cfg.triang_show_reprojection = self.show_reproj.isChecked()

        self.run_widget.set_running(True)
        self.run_widget.log.append(
            f"[INFO] Triangulation | Reproj threshold: {cfg.triang_reproj_error_threshold}px | "
            f"Min cams: {cfg.triang_min_cameras}"
        )

        def run_triang():
            try:
                from Pose2Sim import Pose2Sim
                Pose2Sim.triangulation()
            except ImportError:
                raise RuntimeError("pose2sim is not installed.")

        self.worker = PipelineWorker("Triangulation", run_triang)
        self.worker.log_signal.connect(self.run_widget.log_message)
        self.worker.progress_signal.connect(self.run_widget.set_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _abort(self):
        if self.worker:
            self.worker.terminate()
        self.run_widget.set_running(False)
        self.run_widget.log.append("[WARNING] Aborted.")

    def _on_finished(self, success, msg):
        self.run_widget.set_done(success, msg)
        if success:
            self.pm.set_step_status(4, StepStatus.DONE)
