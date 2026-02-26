"""
ui/tabs/tab_setup.py - Project Setup Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QSpinBox, QFormLayout, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.components.widgets import PathPicker
from app.project import ProjectManager, StepStatus


class SetupTab(QWidget):
    project_created = pyqtSignal()

    def __init__(self, pm: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = pm
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        title = QLabel("Project Setup")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        desc = QLabel("Create a new Pose2Sim project or open an existing one.")
        desc.setObjectName("sectionDesc")
        layout.addWidget(desc)

        # ── New Project ──────────────────────────────────────
        new_group = QGroupBox("New Project")
        new_layout = QFormLayout(new_group)
        new_layout.setSpacing(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. basketball_jump")
        new_layout.addRow("Project Name:", self.name_edit)

        self.dir_picker = PathPicker(mode="dir", placeholder="Choose output folder...")
        new_layout.addRow("Project Directory:", self.dir_picker)

        # Camera count
        cam_widget = QWidget()
        cam_layout = QHBoxLayout(cam_widget)
        cam_layout.setContentsMargins(0, 0, 0, 0)
        cam_layout.setSpacing(12)
        self.cam_group = QButtonGroup(self)
        for n in [2, 3, 4]:
            rb = QRadioButton(f"{n} Cameras")
            if n == 2:
                rb.setChecked(True)
            self.cam_group.addButton(rb, n)
            cam_layout.addWidget(rb)
        cam_layout.addStretch()
        new_layout.addRow("Camera Count:", cam_widget)

        # Pose estimator
        pose_widget = QWidget()
        pose_layout = QHBoxLayout(pose_widget)
        pose_layout.setContentsMargins(0, 0, 0, 0)
        pose_layout.setSpacing(12)
        self.pose_group = QButtonGroup(self)
        for name in ["RTMLib", "OpenPose"]:
            rb = QRadioButton(name)
            if name == "RTMLib":
                rb.setChecked(True)
            self.pose_group.addButton(rb, 0 if name == "RTMLib" else 1)
            pose_layout.addWidget(rb)
        pose_layout.addStretch()
        new_layout.addRow("Pose Estimator:", pose_widget)

        # OpenPose path (hidden unless selected)
        self.openpose_picker = PathPicker(mode="dir", placeholder="Path to OpenPose installation...")
        self.openpose_picker.setVisible(False)
        new_layout.addRow("OpenPose Path:", self.openpose_picker)
        self.pose_group.buttonToggled.connect(self._on_estimator_toggled)

        # Create button
        create_btn = QPushButton("Create Project")
        create_btn.setObjectName("primaryBtn")
        create_btn.setFixedWidth(160)
        create_btn.clicked.connect(self._create_project)
        new_layout.addRow("", create_btn)

        layout.addWidget(new_group)

        # ── Open Existing Project ────────────────────────────
        open_group = QGroupBox("Open Existing Project")
        open_outer = QVBoxLayout(open_group)
        open_outer.setSpacing(10)

        # Folder picker row
        folder_row = QHBoxLayout()
        self.open_folder_edit = QLineEdit()
        self.open_folder_edit.setPlaceholderText("Select your project folder...")
        self.open_folder_edit.setReadOnly(True)
        folder_row.addWidget(self.open_folder_edit)

        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browseBtn")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_existing_folder)
        folder_row.addWidget(browse_btn)
        open_outer.addLayout(folder_row)

        # Status hint (shows what was found in the folder)
        self.open_hint = QLabel("")
        self.open_hint.setStyleSheet("color: #8b949e; font-size: 11px; padding-left: 2px;")
        open_outer.addWidget(self.open_hint)

        # Open button
        self.open_btn = QPushButton("Open Project")
        self.open_btn.setObjectName("primaryBtn")
        self.open_btn.setFixedWidth(130)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_existing_folder)
        open_outer.addWidget(self.open_btn, alignment=Qt.AlignLeft)

        layout.addWidget(open_group)

        # ── Current Project Info ─────────────────────────────
        info_group = QGroupBox("Current Project")
        info_layout = QFormLayout(info_group)

        self.info_name = QLabel("—")
        self.info_name.setStyleSheet("color: #58a6ff;")
        info_layout.addRow("Name:", self.info_name)

        self.info_dir = QLabel("—")
        self.info_dir.setWordWrap(True)
        info_layout.addRow("Directory:", self.info_dir)

        self.info_cameras = QLabel("—")
        info_layout.addRow("Cameras:", self.info_cameras)

        self.info_estimator = QLabel("—")
        info_layout.addRow("Estimator:", self.info_estimator)

        layout.addWidget(info_group)
        layout.addStretch()

        # Update display when project changes
        self.pm.register_change_callback(self._refresh_info)

    # ── Handlers ────────────────────────────────────────────

    def _on_estimator_toggled(self):
        is_openpose = self.pose_group.checkedId() == 1
        self.openpose_picker.setVisible(is_openpose)

    def _browse_existing_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if not folder:
            return

        self.open_folder_edit.setText(folder)

        # Auto-detect what's inside the folder
        config_path = os.path.join(folder, "markerless_config.json")
        cam_dirs = [
            d for d in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, d)) and d.startswith("cam")
        ]

        if os.path.exists(config_path):
            self.open_hint.setText("✓ markerless_config.json found — project will be fully restored.")
            self.open_hint.setStyleSheet("color: #7ee787; font-size: 11px; padding-left: 2px;")
        elif cam_dirs:
            cam_dirs_sorted = sorted(cam_dirs)
            self.open_hint.setText(
                f"⚠ No config file found, but camera folders detected: {', '.join(cam_dirs_sorted)}\n"
                f"  Project will be initialized from this folder structure."
            )
            self.open_hint.setStyleSheet("color: #e3b341; font-size: 11px; padding-left: 2px;")
        else:
            self.open_hint.setText("⚠ No config or camera folders found. An empty project will be created here.")
            self.open_hint.setStyleSheet("color: #e3b341; font-size: 11px; padding-left: 2px;")

        self.open_btn.setEnabled(True)

    def _open_existing_folder(self):
        folder = self.open_folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid project folder first.")
            return

        config_path = os.path.join(folder, "markerless_config.json")

        try:
            if os.path.exists(config_path):
                # Best case: load saved config
                self.pm.load_project(config_path)
            else:
                # Fallback: infer from folder structure
                project_name = os.path.basename(folder)
                cam_dirs = sorted([
                    d for d in os.listdir(folder)
                    if os.path.isdir(os.path.join(folder, d)) and d.startswith("cam")
                ])
                camera_count = len(cam_dirs) if 2 <= len(cam_dirs) <= 4 else 2

                self.pm.new_project(folder, project_name, camera_count, "RTMLib")
                self.pm.config.save(config_path)

            self.pm.set_step_status(0, StepStatus.DONE)
            self.project_created.emit()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def _create_project(self):
        name = self.name_edit.text().strip()
        base_dir = self.dir_picker.path().strip()

        if not name:
            QMessageBox.warning(self, "Missing Info", "Please enter a project name.")
            return
        if not base_dir:
            QMessageBox.warning(self, "Missing Info", "Please select a project directory.")
            return

        project_dir = os.path.join(base_dir, name)
        camera_count = self.cam_group.checkedId()
        estimator = "RTMLib" if self.pose_group.checkedId() == 0 else "OpenPose"

        try:
            self.pm.new_project(project_dir, name, camera_count, estimator)
            if estimator == "OpenPose":
                self.pm.update(openpose_path=self.openpose_picker.path())

            # Create camera subfolders
            for i in range(1, camera_count + 1):
                os.makedirs(os.path.join(project_dir, f"cam{i:02d}"), exist_ok=True)
                os.makedirs(os.path.join(project_dir, "calibration", f"cam{i:02d}"), exist_ok=True)

            self.pm.config.save(os.path.join(project_dir, "markerless_config.json"))
            self.pm.set_step_status(0, StepStatus.DONE)
            self.project_created.emit()

            QMessageBox.information(self, "Project Created",
                f"Project '{name}' created at:\n{project_dir}\n\n"
                f"Camera folders (cam01–cam{camera_count:02d}) have been created.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create project:\n{e}")

    def _refresh_info(self, cfg):
        self.info_name.setText(cfg.project_name or "—")
        self.info_dir.setText(cfg.project_dir or "—")
        self.info_cameras.setText(str(cfg.camera_count) if cfg.project_name else "—")
        self.info_estimator.setText(cfg.pose_estimator if cfg.project_name else "—")
