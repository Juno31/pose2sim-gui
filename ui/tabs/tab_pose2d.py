"""
ui/tabs/tab_pose2d.py - 2D Pose Estimation Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QComboBox, QCheckBox, QFormLayout, QSplitter, QSpinBox, QPushButton
)
from PyQt5.QtCore import Qt, QTimer

from ui.components.widgets import PathPicker, StepRunWidget
from ui.tabs.pose2d_preview import PosePreviewWidget
from app.project import ProjectManager, StepStatus
import sys
from app.runner import ScriptWorker

# Mapping between GUI combo text and Config.toml pose_model values
_MODEL_TO_TOML = {
    "body":       "Body_with_feet",
    "wholebody":  "Whole_body_wrist",
    "hand":       "Hand",
    "face":       "Face",
}
_TOML_TO_MODEL = {v.lower(): k for k, v in _MODEL_TO_TOML.items()}
_TOML_TO_MODEL["body"] = "body"           # COCO_17 fallback
_TOML_TO_MODEL["whole_body"] = "wholebody"


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

        self.splitter = QSplitter(Qt.Vertical)

        # Config
        config_widget = QWidget()
        config_layout = QHBoxLayout(config_widget)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)
        config_layout.addWidget(self._build_estimator_group())
        config_layout.addWidget(self._build_video_group())
        self.splitter.addWidget(config_widget)

        # Run
        self.run_widget = StepRunWidget("Run 2D Pose Estimation")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        self.splitter.addWidget(self.run_widget)

        # Inline pose preview (collapsed until estimation completes)
        self.preview_widget = PosePreviewWidget()
        self.splitter.addWidget(self.preview_widget)

        # Start with preview pane collapsed
        self.splitter.setSizes([300, 250, 0])

        outer.addWidget(self.splitter)

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

        self.rtmlib_mode = QComboBox()
        self.rtmlib_mode.addItems(["balanced", "lightweight", "performance"])
        layout.addRow("Mode:", self.rtmlib_mode)

        self.rtmlib_backend = QComboBox()
        self.rtmlib_backend.addItems(["auto", "onnxruntime", "opencv", "openvino"])
        layout.addRow("Backend:", self.rtmlib_backend)

        self.rtmlib_device = QComboBox()
        self.rtmlib_device.addItems(["auto", "cpu", "cuda", "mps"])
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

        self.display_detection = QCheckBox("Display detection in real time")
        self.display_detection.setChecked(True)
        layout.addRow(self.display_detection)

        self.handle_lr_swap = QCheckBox("Handle left/right swap")
        self.handle_lr_swap.setToolTip("Useful when cameras film from the sagittal plane")
        layout.addRow(self.handle_lr_swap)

        self.undistort_points = QCheckBox("Undistort keypoints")
        self.undistort_points.setToolTip("Better accuracy if lens distortion is significant")
        layout.addRow(self.undistort_points)

        self.det_frequency = QSpinBox()
        self.det_frequency.setRange(1, 60)
        self.det_frequency.setValue(4)
        self.det_frequency.setToolTip("Run person detection every N frames (tracking in between)")
        layout.addRow("Det. Frequency:", self.det_frequency)

        self.tracking_mode = QComboBox()
        self.tracking_mode.addItems(["sports2d", "none", "deepsort"])
        self.tracking_mode.setToolTip("Tracking method between detection frames")
        layout.addRow("Tracking Mode:", self.tracking_mode)

        self.save_video_mode = QComboBox()
        self.save_video_mode.addItems(["to_video", "to_images", "none"])
        self.save_video_mode.setToolTip("How to save the pose output")
        layout.addRow("Save Output:", self.save_video_mode)

        self.vid_img_ext = QComboBox()
        self.vid_img_ext.addItems(["mp4", "avi", "mov", "mkv", "jpg", "png"])
        self.vid_img_ext.setToolTip("Extension of input video/image files")
        layout.addRow("Video Extension:", self.vid_img_ext)

        return group

    def _build_video_group(self):
        group = QGroupBox("Video Inputs")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        info = QLabel(
            "Pose2Sim expects one video file per camera,\n"
            "named cam01.mp4 … camNN.mp4, all placed flat\n"
            "inside the project's videos/ folder:\n\n"
            "  project/videos/cam01.mp4\n"
            "  project/videos/cam02.mp4  …"
        )
        info.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(info)

        # Single folder picker that points at the videos/ directory
        self.videos_picker = PathPicker(
            label="videos/ folder:",
            mode="dir",
            placeholder="project/videos",
        )
        layout.addWidget(self.videos_picker)

        # Per-camera file status labels (read-only, updated on project change)
        self.cam_status_layout = QVBoxLayout()
        layout.addLayout(self.cam_status_layout)
        layout.addStretch()

        self.cam_pickers = []   # kept for API compatibility
        return group

    def load_from_toml(self, data: dict):
        """Populate widgets from a parsed Config.toml dict."""
        pose = data.get("pose", {})

        # pose_model
        pose_model = pose.get("pose_model", "")
        gui_key = _TOML_TO_MODEL.get(pose_model.lower())
        if gui_key:
            idx = self.rtmlib_model.findText(gui_key)
            if idx >= 0:
                self.rtmlib_model.setCurrentIndex(idx)

        # mode
        mode = pose.get("mode", "")
        if isinstance(mode, str) and mode in ("balanced", "lightweight", "performance"):
            idx = self.rtmlib_mode.findText(mode)
            if idx >= 0:
                self.rtmlib_mode.setCurrentIndex(idx)

        # backend
        backend = pose.get("backend", "auto").lower()
        idx = self.rtmlib_backend.findText(backend)
        if idx >= 0:
            self.rtmlib_backend.setCurrentIndex(idx)

        # device
        device = pose.get("device", "auto").lower()
        idx = self.rtmlib_device.findText(device)
        if idx >= 0:
            self.rtmlib_device.setCurrentIndex(idx)

        # overwrite
        overwrite = pose.get("overwrite_pose", False)
        self.overwrite.setChecked(bool(overwrite))

        val = pose.get("display_detection")
        if isinstance(val, bool):
            self.display_detection.setChecked(val)

        val = pose.get("handle_LR_swap")
        if isinstance(val, bool):
            self.handle_lr_swap.setChecked(val)

        val = pose.get("undistort_points")
        if isinstance(val, bool):
            self.undistort_points.setChecked(val)

        val = pose.get("det_frequency")
        if isinstance(val, int):
            self.det_frequency.setValue(val)

        val = pose.get("tracking_mode")
        if isinstance(val, str):
            idx = self.tracking_mode.findText(val)
            if idx >= 0:
                self.tracking_mode.setCurrentIndex(idx)

        val = pose.get("save_video")
        if isinstance(val, str):
            idx = self.save_video_mode.findText(val)
            if idx >= 0:
                self.save_video_mode.setCurrentIndex(idx)

        val = pose.get("vid_img_extension")
        if isinstance(val, str):
            idx = self.vid_img_ext.findText(val)
            if idx >= 0:
                self.vid_img_ext.setCurrentIndex(idx)

    def _save_config(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.save_status.setText("✗ No project loaded")
            self.save_status.setStyleSheet("color: #f85149; font-size: 11px;")
            return
        from app.toml_bridge import save_toml_values
        toml_model = _MODEL_TO_TOML.get(self.rtmlib_model.currentText(), "Body_with_feet")
        save_toml_values(cfg.project_dir, [
            ("pose", "pose_model",        toml_model),
            ("pose", "mode",              self.rtmlib_mode.currentText()),
            ("pose", "backend",           self.rtmlib_backend.currentText()),
            ("pose", "device",            self.rtmlib_device.currentText()),
            ("pose", "overwrite_pose",    self.overwrite.isChecked()),
            ("pose", "display_detection", self.display_detection.isChecked()),
            ("pose", "handle_LR_swap",    self.handle_lr_swap.isChecked()),
            ("pose", "undistort_points",  self.undistort_points.isChecked()),
            ("pose", "det_frequency",     self.det_frequency.value()),
            ("pose", "tracking_mode",     self.tracking_mode.currentText()),
            ("pose", "save_video",        self.save_video_mode.currentText()),
            ("pose", "vid_img_extension", self.vid_img_ext.currentText()),
        ])
        self.save_status.setText("✓ Config saved")
        self.save_status.setStyleSheet("color: #7ee787; font-size: 11px;")
        QTimer.singleShot(3000, lambda: self.save_status.setText(""))

    def _on_project_changed(self, cfg):
        # Clear per-camera status labels
        while self.cam_status_layout.count():
            item = self.cam_status_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cam_pickers.clear()

        if cfg.project_dir:
            videos_dir = os.path.join(cfg.project_dir, "videos")
            self.videos_picker.set_path(videos_dir)

            for i in range(1, cfg.camera_count + 1):
                expected = os.path.join(videos_dir, f"cam{i:02d}.mp4")
                found = os.path.isfile(expected)
                icon = "✓" if found else "✗"
                color = "#7ee787" if found else "#f85149"
                lbl = QLabel(f'<span style="color:{color};">{icon}</span>'
                             f'  cam{i:02d}.mp4'
                             + ("" if found else "  ← not found"))
                lbl.setStyleSheet("font-size: 12px;")
                self.cam_status_layout.addWidget(lbl)

        # Update estimator label
        self.estimator_label.setText(cfg.pose_estimator)
        is_rtmlib = cfg.pose_estimator == "RTMLib"
        self.rtmlib_model.setEnabled(is_rtmlib)
        self.rtmlib_mode.setEnabled(is_rtmlib)
        self.rtmlib_backend.setEnabled(is_rtmlib)
        self.rtmlib_device.setEnabled(is_rtmlib)
        self.op_model.setEnabled(not is_rtmlib)
        self.op_scale.setEnabled(not is_rtmlib)

        # Load values from Config.toml
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

        # Verify that expected video files exist before launching
        videos_dir = os.path.join(cfg.project_dir, "videos")
        missing = [
            f"cam{i:02d}.mp4"
            for i in range(1, cfg.camera_count + 1)
            if not os.path.isfile(os.path.join(videos_dir, f"cam{i:02d}.mp4"))
        ]
        if missing:
            self.run_widget.log.append(
                f"[ERROR] Missing video files in {videos_dir}:\n"
                + "\n".join(f"  {m}" for m in missing)
            )
            self.run_widget.log.append(
                "[ERROR] Pose2Sim expects videos named cam01.mp4, cam02.mp4 … "
                "placed directly inside the videos/ folder."
            )
            return


        if cfg.pose_estimator == "RTMLib":
            cfg.rtmlib_model = self.rtmlib_model.currentText()

        self.run_widget.set_running(True)
        self.run_widget.log.append(f"[INFO] Estimator: {cfg.pose_estimator}")
        self.run_widget.log.append(f"[INFO] Cameras: {cfg.camera_count}")
        if cfg.pose_estimator == "RTMLib":
            self.run_widget.log.append(
                f"[INFO] Model: {cfg.rtmlib_model} | "
                f"Backend: {self.rtmlib_backend.currentText()} | "
                f"Device: {self.rtmlib_device.currentText()}"
            )

        cmd = [sys.executable, '-c',
               f'import os; os.chdir({repr(cfg.project_dir)}); '
               f'from Pose2Sim import Pose2Sim; Pose2Sim.poseEstimation()']
        self.worker = ScriptWorker(cmd, cwd=cfg.project_dir)
        self.worker.log_signal.connect(self.run_widget.log_message)
        self.worker.progress_signal.connect(self.run_widget.set_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _abort(self):
        if self.worker:
            self.worker.abort()
        self.run_widget.set_running(False)
        self.run_widget.log.append("[WARNING] Aborted by user.")

    def _on_finished(self, success, msg):
        self.run_widget.set_done(success, msg)
        if success:
            self.pm.set_step_status(2, StepStatus.DONE)
            cfg = self.pm.config
            self.preview_widget.load(cfg.project_dir, cfg.camera_count)
            self.splitter.setSizes([220, 180, 400])

    def hideEvent(self, event):
        """Release VideoCapture resources when tab is hidden."""
        super().hideEvent(event)

    def closeEvent(self, event):
        self.preview_widget.cleanup()
        super().closeEvent(event)
