"""
ui/tabs/tab_visualization.py - 3D Visualization Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout,
    QSpinBox, QCheckBox, QSplitter, QPushButton, QHBoxLayout
)
from PyQt5.QtCore import Qt
from ui.components.widgets import StepRunWidget, PathPicker
from app.project import ProjectManager, StepStatus
from app.runner import PipelineWorker


class VisualizationTab(QWidget):
    def __init__(self, pm: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = pm
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("3D Visualization")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Visualize reconstructed 3D markers and skeletal motion. Optionally export as video.")
        desc.setObjectName("sectionDesc")
        outer.addWidget(desc)

        splitter = QSplitter(Qt.Vertical)

        # Settings
        group = QGroupBox("Visualization Settings")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.marker_size = QSpinBox()
        self.marker_size.setRange(1, 50)
        self.marker_size.setValue(15)
        self.marker_size.setSuffix(" px")
        form.addRow("Marker Size:", self.marker_size)

        self.line_width = QSpinBox()
        self.line_width.setRange(1, 10)
        self.line_width.setValue(3)
        self.line_width.setSuffix(" px")
        form.addRow("Line Width:", self.line_width)

        self.show_axes = QCheckBox("Show 3D axes")
        self.show_axes.setChecked(True)
        form.addRow(self.show_axes)

        self.save_video = QCheckBox("Save animation as video")
        self.save_video.setChecked(True)
        form.addRow(self.save_video)

        splitter.addWidget(group)

        # Run + quick-open buttons
        run_container = QWidget()
        run_layout = QVBoxLayout(run_container)
        run_layout.setContentsMargins(0, 0, 0, 0)

        quick_btns = QHBoxLayout()
        open_c3d_btn = QPushButton("Open .c3d in Mokka")
        open_c3d_btn.clicked.connect(self._open_c3d)
        quick_btns.addWidget(open_c3d_btn)

        open_trc_btn = QPushButton("Open .trc in OpenSim")
        open_trc_btn.clicked.connect(self._open_trc)
        quick_btns.addWidget(open_trc_btn)

        quick_btns.addStretch()
        run_layout.addLayout(quick_btns)

        self.run_widget = StepRunWidget("Run 3D Visualization")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        run_layout.addWidget(self.run_widget)

        splitter.addWidget(run_container)
        splitter.setSizes([280, 380])

        outer.addWidget(splitter)

    def _run(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded.")
            return

        cfg.viz_marker_size = self.marker_size.value()
        cfg.viz_line_width = self.line_width.value()
        cfg.viz_save_video = self.save_video.isChecked()
        cfg.viz_show_axes = self.show_axes.isChecked()

        self.run_widget.set_running(True)
        self.run_widget.log.append(f"[INFO] Viz | Marker: {cfg.viz_marker_size}px | Line: {cfg.viz_line_width}px | Save video: {cfg.viz_save_video}")

        def run_viz():
            try:
                os.chdir(cfg.project_dir)
                from Pose2Sim import Pose2Sim
                Pose2Sim.markerAugmentation()
            except ImportError:
                raise RuntimeError("pose2sim is not installed.")

        self.worker = PipelineWorker("Visualization", run_viz)
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
            self.pm.set_step_status(6, StepStatus.DONE)

    def _open_c3d(self):
        import subprocess, sys
        cfg = self.pm.config
        self.run_widget.log.append("[INFO] Looking for .c3d files in project directory...")
        if cfg.project_dir:
            import glob, os
            files = glob.glob(os.path.join(cfg.project_dir, "**", "*.c3d"), recursive=True)
            if files:
                self.run_widget.log.append(f"[INFO] Found: {files[0]}")
                self.run_widget.log.append("[INFO] Open with Mokka or any C3D viewer.")
            else:
                self.run_widget.log.append("[WARNING] No .c3d files found yet. Run pipeline first.")

    def _open_trc(self):
        cfg = self.pm.config
        self.run_widget.log.append("[INFO] Looking for .trc files in project directory...")
        if cfg.project_dir:
            import glob, os
            files = glob.glob(os.path.join(cfg.project_dir, "**", "*.trc"), recursive=True)
            if files:
                self.run_widget.log.append(f"[INFO] Found: {files[0]}")
                self.run_widget.log.append("[INFO] Open with OpenSim or any TRC viewer.")
            else:
                self.run_widget.log.append("[WARNING] No .trc files found yet. Run pipeline first.")
