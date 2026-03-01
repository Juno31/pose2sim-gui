"""
ui/tabs/tab_calibration.py - Calibration Tab (Intrinsic + Extrinsic)
"""

import os
import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QComboBox, QDoubleSpinBox, QSpinBox, QFormLayout,
    QTabWidget, QCheckBox, QSplitter, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer

from ui.components.widgets import PathPicker, StepRunWidget
from app.project import ProjectManager, StepStatus
import sys
from app.runner import ScriptWorker


class CalibrationTab(QWidget):
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

        # Header
        title = QLabel("Calibration")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Camera calibration: intrinsic parameters (lens distortion) and extrinsic parameters (camera positions).")
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

        # Top: config panels
        config_widget = QWidget()
        config_layout = QHBoxLayout(config_widget)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)

        config_layout.addWidget(self._build_intrinsic_group())
        config_layout.addWidget(self._build_extrinsic_group())

        splitter.addWidget(config_widget)

        # Bottom: run widget
        self.run_widget = StepRunWidget("Run Calibration")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)

        splitter.setSizes([350, 300])
        outer.addWidget(splitter)

    def _build_intrinsic_group(self):
        group = QGroupBox("Intrinsic Calibration")
        layout = QFormLayout(group)
        layout.setSpacing(10)

        self.intrinsic_type = QComboBox()
        self.intrinsic_type.addItems(["checkerboard", "charuco", "none (skip)"])
        self.intrinsic_type.currentTextChanged.connect(self._on_intrinsic_type_changed)
        layout.addRow("Method:", self.intrinsic_type)

        self.checker_cols = QSpinBox()
        self.checker_cols.setRange(3, 20)
        self.checker_cols.setValue(6)
        layout.addRow("Columns:", self.checker_cols)

        self.checker_rows = QSpinBox()
        self.checker_rows.setRange(3, 20)
        self.checker_rows.setValue(9)
        layout.addRow("Rows:", self.checker_rows)

        self.square_size = QDoubleSpinBox()
        self.square_size.setRange(1.0, 500.0)
        self.square_size.setValue(40.0)
        self.square_size.setSuffix(" mm")
        layout.addRow("Square Size:", self.square_size)

        self.extract_every_n = QDoubleSpinBox()
        self.extract_every_n.setRange(0.1, 30.0)
        self.extract_every_n.setValue(1.0)
        self.extract_every_n.setSuffix(" s")
        self.extract_every_n.setToolTip("Extract a frame every N seconds from intrinsic calibration video")
        layout.addRow("Extract Every:", self.extract_every_n)

        self.intrinsics_ext = QComboBox()
        self.intrinsics_ext.addItems(["jpg", "png", "mp4", "avi", "mov"])
        self.intrinsics_ext.setToolTip("File extension for intrinsic calibration images or video")
        layout.addRow("Image Extension:", self.intrinsics_ext)

        self.overwrite_intrinsics = QCheckBox("Overwrite existing intrinsics")
        layout.addRow(self.overwrite_intrinsics)

        self.show_detection_intr = QCheckBox("Show corner detection on images")
        self.show_detection_intr.setChecked(True)
        layout.addRow(self.show_detection_intr)

        # Camera video folders
        lbl = QLabel("Calibration Videos per Camera:")
        lbl.setStyleSheet("color: #8b949e; margin-top: 8px;")
        layout.addRow(lbl)

        self.cam_video_pickers = []
        # Will be populated on project change

        return group

    def _build_extrinsic_group(self):
        group = QGroupBox("Extrinsic Calibration")
        layout = QFormLayout(group)
        layout.setSpacing(10)

        self.extrinsic_type = QComboBox()
        self.extrinsic_type.addItems(["scene", "board"])
        layout.addRow("Method:", self.extrinsic_type)

        info = QLabel(
            "• scene: manually annotate points in the scene\n"
            "• board: use a calibration board visible in all cameras"
        )
        info.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addRow(info)

        self.scene_picker = PathPicker(mode="file", filter="Config Files (*.toml *.json *.yaml)",
                                       placeholder="extrinsic_scene.toml")
        layout.addRow("Scene Config:", self.scene_picker)

        self.show_distorted = QCheckBox("Show distorted frames during calibration")
        layout.addRow(self.show_distorted)

        self.extrinsics_ext = QComboBox()
        self.extrinsics_ext.addItems(["png", "jpg", "mp4", "avi", "mov"])
        self.extrinsics_ext.setToolTip("File extension for extrinsic calibration images or video")
        layout.addRow("Image Extension:", self.extrinsics_ext)

        self.show_reproj_error = QCheckBox("Show reprojection error")
        self.show_reproj_error.setChecked(True)
        layout.addRow(self.show_reproj_error)

        self.save_debug_images = QCheckBox("Save debug images with clicked points")
        self.save_debug_images.setChecked(True)
        layout.addRow(self.save_debug_images)

        return group

    def _on_intrinsic_type_changed(self, text):
        enabled = text != "none (skip)"
        self.checker_cols.setEnabled(enabled)
        self.checker_rows.setEnabled(enabled)
        self.square_size.setEnabled(enabled)

    def load_from_toml(self, data: dict):
        """Populate widgets from a parsed Config.toml dict."""
        calc = data.get("calibration", {}).get("calculate", {})
        intrinsics = calc.get("intrinsics", {})

        corners = intrinsics.get("intrinsics_corners_nb")
        if isinstance(corners, (list, tuple)) and len(corners) == 2:
            self.checker_cols.setValue(int(corners[0]))
            self.checker_rows.setValue(int(corners[1]))

        sq = intrinsics.get("intrinsics_square_size")
        if sq is not None:
            try:
                self.square_size.setValue(float(sq))
            except (TypeError, ValueError):
                pass

        val = intrinsics.get("extract_every_N_sec")
        if isinstance(val, (int, float)):
            self.extract_every_n.setValue(float(val))

        val = intrinsics.get("intrinsics_extension")
        if isinstance(val, str):
            idx = self.intrinsics_ext.findText(val)
            if idx >= 0:
                self.intrinsics_ext.setCurrentIndex(idx)

        val = intrinsics.get("overwrite_intrinsics")
        if isinstance(val, bool):
            self.overwrite_intrinsics.setChecked(val)

        val = intrinsics.get("show_detection_intrinsics")
        if isinstance(val, bool):
            self.show_detection_intr.setChecked(val)

        extrinsics = calc.get("extrinsics", {})
        method = extrinsics.get("extrinsics_method")
        if method:
            idx = self.extrinsic_type.findText(method)
            if idx >= 0:
                self.extrinsic_type.setCurrentIndex(idx)

        val = extrinsics.get("extrinsics_extension")
        if isinstance(val, str):
            idx = self.extrinsics_ext.findText(val)
            if idx >= 0:
                self.extrinsics_ext.setCurrentIndex(idx)

        val = extrinsics.get("show_reprojection_error")
        if isinstance(val, bool):
            self.show_reproj_error.setChecked(val)

        val = calc.get("save_debug_images")
        if isinstance(val, bool):
            self.save_debug_images.setChecked(val)

    def _save_config(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.save_status.setText("✗ No project loaded")
            self.save_status.setStyleSheet("color: #f85149; font-size: 11px;")
            return
        from app.toml_bridge import save_toml_values
        save_toml_values(cfg.project_dir, [
            ("calibration.calculate.intrinsics", "intrinsics_corners_nb",
             [self.checker_cols.value(), self.checker_rows.value()]),
            ("calibration.calculate.intrinsics", "intrinsics_square_size",
             self.square_size.value()),
            ("calibration.calculate.intrinsics", "extract_every_N_sec",
             self.extract_every_n.value()),
            ("calibration.calculate.intrinsics", "intrinsics_extension",
             self.intrinsics_ext.currentText()),
            ("calibration.calculate.intrinsics", "overwrite_intrinsics",
             self.overwrite_intrinsics.isChecked()),
            ("calibration.calculate.intrinsics", "show_detection_intrinsics",
             self.show_detection_intr.isChecked()),
            ("calibration.calculate.extrinsics", "extrinsics_method",
             self.extrinsic_type.currentText()),
            ("calibration.calculate.extrinsics", "extrinsics_extension",
             self.extrinsics_ext.currentText()),
            ("calibration.calculate.extrinsics", "show_reprojection_error",
             self.show_reproj_error.isChecked()),
            ("calibration.calculate",            "save_debug_images",
             self.save_debug_images.isChecked()),
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

    def _collect_config(self):
        cfg = self.pm.config
        cfg.calib_intrinsic_type = self.intrinsic_type.currentText().split()[0]
        cfg.calib_extrinsic_type = self.extrinsic_type.currentText()
        cfg.checkerboard_cols = self.checker_cols.value()
        cfg.checkerboard_rows = self.checker_rows.value()
        cfg.square_size_mm = self.square_size.value()
        cfg.calib_scene_file = self.scene_picker.path()

    def _patch_config_toml(self, project_dir: str):
        """
        Pose2Sim bug workaround: when show_detection_intrinsics=true, calibration.py
        line 770 unpacks findCorners() into two variables, but the function returns only
        one value when objp is empty (happens on re-runs with a partial Image_points.json).
        Force non-interactive mode so the single-return code path is used instead.
        Comments in Config.toml are preserved via regex substitution.
        """
        toml_path = os.path.join(project_dir, "Config.toml")
        if not os.path.exists(toml_path):
            return

        try:
            with open(toml_path, "r", encoding="utf-8") as f:
                content = f.read()

            patched = re.sub(
                r'(show_detection_intrinsics\s*=\s*)true',
                r'\1false',
                content,
            )

            if patched != content:
                with open(toml_path, "w", encoding="utf-8") as f:
                    f.write(patched)
                self.run_widget.log.append(
                    "[INFO] Config.toml: set show_detection_intrinsics=false "
                    "(automatic corner detection — required for subprocess mode)"
                )
        except Exception as exc:
            self.run_widget.log.append(f"[WARNING] Could not patch Config.toml: {exc}")

    def _run(self):
        self._collect_config()
        cfg = self.pm.config

        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded. Please set up a project first.")
            return

        self.run_widget.set_running(True)
        self.run_widget.log.append(f"[INFO] Project: {cfg.project_dir}")
        self.run_widget.log.append(f"[INFO] Intrinsic: {cfg.calib_intrinsic_type} | Extrinsic: {cfg.calib_extrinsic_type}")
        self.run_widget.log.append(f"[INFO] Board: {cfg.checkerboard_cols}x{cfg.checkerboard_rows}, {cfg.square_size_mm}mm squares")

        self._patch_config_toml(cfg.project_dir)

        cmd = [sys.executable, '-c',
               f'import os; os.chdir({repr(cfg.project_dir)}); '
               f'from Pose2Sim import Pose2Sim; Pose2Sim.calibration()']
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

    def _on_finished(self, success: bool, msg: str):
        self.run_widget.set_done(success, msg)
        if success:
            self.pm.set_step_status(1, StepStatus.DONE)
