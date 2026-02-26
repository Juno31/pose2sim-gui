"""
ui/tabs/tab_pose2d.py - 2D Pose Estimation Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QComboBox, QCheckBox, QFormLayout, QSplitter, QSpinBox
)
from PyQt5.QtCore import Qt

from ui.components.widgets import PathPicker, StepRunWidget
from app.project import ProjectManager, StepStatus
from app.runner import PipelineWorker


class Pose2DTab(QWidget):
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

        title = QLabel("2D Pose Estimation")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Detect 2D body keypoints in each camera view using the selected pose estimator.")
        desc.setObjectName("sectionDesc")
        outer.addWidget(desc)

        splitter = QSplitter(Qt.Vertical)

        # Config
        config_widget = QWidget()
        config_layout = QHBoxLayout(config_widget)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)
        config_layout.addWidget(self._build_estimator_group())
        config_layout.addWidget(self._build_video_group())
        splitter.addWidget(config_widget)

        # Run
        self.run_widget = StepRunWidget("Run 2D Pose Estimation")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)
        splitter.setSizes([350, 300])

        outer.addWidget(splitter)

    def _build_estimator_group(self):
        group = QGroupBox("Estimator Settings")
        layout = QFormLayout(group)
        layout.setSpacing(10)

        self.estimator_label = QLabel("RTMLib")
        self.estimator_label.setStyleSheet("color: #58a6ff; font-weight: bold;")
        layout.addRow("Active Estimator:", self.estimator_label)

        # RTMLib options
        self.rtmlib_model = QComboBox()
        self.rtmlib_model.addItems(["body", "wholebody", "hand", "face"])
        layout.addRow("RTMLib Model:", self.rtmlib_model)

        self.rtmlib_backend = QComboBox()
        self.rtmlib_backend.addItems(["onnxruntime", "opencv", "openvino"])
        layout.addRow("Backend:", self.rtmlib_backend)

        self.rtmlib_device = QComboBox()
        self.rtmlib_device.addItems(["cpu", "cuda", "mps"])
        layout.addRow("Device:", self.rtmlib_device)

        # Detection thresholds
        self.det_threshold = QLabel("0.3")
        layout.addRow("Det. Threshold:", self.det_threshold)

        # OpenPose options (shown if selected)
        self.op_model = QComboBox()
        self.op_model.addItems(["BODY_25", "COCO", "MPI"])
        self.op_model.setEnabled(False)
        layout.addRow("OpenPose Model:", self.op_model)

        self.op_scale = QSpinBox()
        self.op_scale.setRange(1, 4)
        self.op_scale.setValue(1)
        self.op_scale.setEnabled(False)
        layout.addRow("Scale Number:", self.op_scale)

        self.overwrite = QCheckBox("Overwrite existing pose files")
        layout.addRow(self.overwrite)

        return group

    def _build_video_group(self):
        group = QGroupBox("Video Inputs")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        info = QLabel("Place videos in each camera folder:\nproject/cam01/video.mp4\nproject/cam02/video.mp4 ...")
        info.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(info)

        self.cam_pickers_layout = QVBoxLayout()
        layout.addLayout(self.cam_pickers_layout)
        layout.addStretch()

        self.cam_pickers = []
        return group

    def _on_project_changed(self, cfg):
        # Clear and rebuild camera pickers
        while self.cam_pickers_layout.count():
            item = self.cam_pickers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cam_pickers.clear()

        for i in range(1, cfg.camera_count + 1):
            picker = PathPicker(label=f"cam{i:02d}:", mode="dir",
                                placeholder=f"Video folder for camera {i}")
            if cfg.project_dir:
                default = os.path.join(cfg.project_dir, f"cam{i:02d}")
                picker.set_path(default)
            self.cam_pickers.append(picker)
            self.cam_pickers_layout.addWidget(picker)

        # Update estimator label
        self.estimator_label.setText(cfg.pose_estimator)
        is_rtmlib = cfg.pose_estimator == "RTMLib"
        self.rtmlib_model.setEnabled(is_rtmlib)
        self.rtmlib_backend.setEnabled(is_rtmlib)
        self.rtmlib_device.setEnabled(is_rtmlib)
        self.op_model.setEnabled(not is_rtmlib)
        self.op_scale.setEnabled(not is_rtmlib)

    def _run(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded.")
            return

        # Update config
        if cfg.pose_estimator == "RTMLib":
            cfg.rtmlib_model = self.rtmlib_model.currentText()

        self.run_widget.set_running(True)
        self.run_widget.log.append(f"[INFO] Estimator: {cfg.pose_estimator}")
        self.run_widget.log.append(f"[INFO] Cameras: {cfg.camera_count}")
        if cfg.pose_estimator == "RTMLib":
            self.run_widget.log.append(f"[INFO] Model: {cfg.rtmlib_model} | Backend: {self.rtmlib_backend.currentText()} | Device: {self.rtmlib_device.currentText()}")

        def run_pose():
            try:
                from Pose2Sim import Pose2Sim
                Pose2Sim.poseEstimation()
            except ImportError:
                raise RuntimeError("pose2sim is not installed. Run: pip install pose2sim")

        self.worker = PipelineWorker("2D Pose Estimation", run_pose)
        self.worker.log_signal.connect(self.run_widget.log_message)
        self.worker.progress_signal.connect(self.run_widget.set_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _abort(self):
        if self.worker:
            self.worker.terminate()
        self.run_widget.set_running(False)
        self.run_widget.log.append("[WARNING] Aborted by user.")

    def _on_finished(self, success, msg):
        self.run_widget.set_done(success, msg)
        if success:
            self.pm.set_step_status(2, StepStatus.DONE)
