"""
ui/main_window.py - Main application window with sidebar navigation
"""

import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QAction,
    QFileDialog, QMessageBox, QStatusBar, QFrame,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, QSettings
from PyQt5.QtGui import QIcon, QFont

from app.project import ProjectManager, StepStatus
from ui.tabs.tab_setup import SetupTab
from ui.tabs.tab_calibration import CalibrationTab
from ui.tabs.tab_pose2d import Pose2DTab
from ui.tabs.tab_sync import SyncTab
from ui.tabs.tab_triangulation import TriangulationTab
from ui.tabs.tab_filtering import FilteringTab
from ui.tabs.tab_visualization import VisualizationTab


STEPS = [
    ("⚙", "Setup",            0),
    ("📐", "Calibration",      1),
    ("🤸", "2D Pose",          2),
    ("🔁", "Synchronization",  3),
    ("📐", "Triangulation",    4),
    ("〰", "Filtering",        5),
    ("🎬", "Visualization",    6),
]

STATUS_ICONS = {
    StepStatus.LOCKED:  "🔒",
    StepStatus.READY:   "○",
    StepStatus.RUNNING: "◉",
    StepStatus.DONE:    "✓",
    StepStatus.ERROR:   "✗",
}


class SidebarButton(QWidget):
    def __init__(self, icon: str, label: str, step_idx: int, parent=None):
        super().__init__(parent)
        self.step_idx = step_idx
        self._clicked_cb = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setFixedWidth(20)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel(label)
        self.text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.text_lbl)

        self.status_lbl = QLabel("○")
        self.status_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_lbl.setFixedWidth(20)
        layout.addWidget(self.status_lbl)

        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self._active = False
        self._enabled = True
        self._apply_style()

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()

    def set_enabled_nav(self, enabled: bool):
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)
        self._apply_style()

    def set_status(self, status: StepStatus):
        icons = {
            StepStatus.LOCKED:  ("🔒", "#30363d"),
            StepStatus.READY:   ("○",  "#8b949e"),
            StepStatus.RUNNING: ("◉",  "#e3b341"),
            StepStatus.DONE:    ("✓",  "#7ee787"),
            StepStatus.ERROR:   ("✗",  "#f85149"),
        }
        icon, color = icons.get(status, ("?", "#8b949e"))
        self.status_lbl.setText(icon)
        self.status_lbl.setStyleSheet(f"color: {color}; font-size: 13px;")

    def _apply_style(self):
        if self._active:
            self.setStyleSheet("""
                SidebarButton {
                    background-color: #1f2937;
                    border-left: 3px solid #58a6ff;
                }
            """)
            self.text_lbl.setStyleSheet("color: #58a6ff; font-weight: bold;")
        elif not self._enabled:
            self.setStyleSheet("SidebarButton { background-color: transparent; }")
            self.text_lbl.setStyleSheet("color: #30363d;")
        else:
            self.setStyleSheet("""
                SidebarButton { background-color: transparent; }
                SidebarButton:hover { background-color: #161b22; }
            """)
            self.text_lbl.setStyleSheet("color: #8b949e;")

    def mousePressEvent(self, event):
        if self._enabled and self._clicked_cb:
            self._clicked_cb(self.step_idx)

    def set_clicked_callback(self, cb):
        self._clicked_cb = cb


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pm = ProjectManager()
        self._settings = QSettings("PerfAnalytics", "Markerless")
        self.setWindowTitle("Markerless")
        self.setMinimumSize(1100, 750)
        self.resize(1280, 800)

        self._build_menu()
        self._build_ui()
        self._build_status_bar()

        self.pm.register_change_callback(self._on_project_changed)

        # Try to restore the last opened project; fall back to Setup tab
        if not self._try_restore_last_project():
            self._go_to_step(0)

    def _build_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar { background-color: #010409; color: #8b949e; border-bottom: 1px solid #21262d; }
            QMenuBar::item:selected { background-color: #21262d; color: #e6edf3; }
            QMenu { background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; }
            QMenu::item:selected { background-color: #1f6feb; }
        """)

        file_menu = menubar.addMenu("File")

        new_act = QAction("New Project", self)
        new_act.setShortcut("Ctrl+N")
        new_act.triggered.connect(lambda: self._go_to_step(0))
        file_menu.addAction(new_act)

        open_act = QAction("Open Project...", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_project_dialog)
        file_menu.addAction(open_act)

        save_act = QAction("Save Project", self)
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self.pm.save_project)
        file_menu.addAction(save_act)

        file_menu.addSeparator()

        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = menubar.addMenu("Help")
        docs_act = QAction("Pose2Sim Documentation", self)
        docs_act.triggered.connect(lambda: self._open_url("https://github.com/perfanalytics/pose2sim"))
        help_menu.addAction(docs_act)

        about_act = QAction("About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(16, 20, 16, 16)

        logo = QLabel("POSE2SIM")
        logo.setStyleSheet("color: #58a6ff; font-size: 16px; font-weight: bold; letter-spacing: 2px;")
        logo_layout.addWidget(logo)

        sub = QLabel("3D Pose Pipeline GUI")
        sub.setStyleSheet("color: #8b949e; font-size: 10px;")
        logo_layout.addWidget(sub)

        sidebar_layout.addWidget(logo_container)

        divider1 = QFrame()
        divider1.setFrameShape(QFrame.HLine)
        divider1.setStyleSheet("color: #21262d;")
        sidebar_layout.addWidget(divider1)

        # Camera info widget
        self.cam_info = QLabel("No project loaded")
        self.cam_info.setStyleSheet("color: #8b949e; font-size: 11px; padding: 10px 16px;")
        sidebar_layout.addWidget(self.cam_info)

        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setStyleSheet("color: #21262d;")
        sidebar_layout.addWidget(divider2)

        # Step buttons
        self.step_buttons = []
        for icon, label, idx in STEPS:
            btn = SidebarButton(icon, label, idx)
            btn.set_clicked_callback(self._go_to_step)
            if idx > 0:
                btn.set_enabled_nav(False)
            self.step_buttons.append(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Run All button at bottom
        run_all_frame = QFrame()
        run_all_frame.setStyleSheet("background-color: #010409; border-top: 1px solid #21262d; padding: 12px;")
        run_all_layout = QVBoxLayout(run_all_frame)

        self.run_all_btn = QPushButton("▶  Run All Steps")
        self.run_all_btn.setObjectName("primaryBtn")
        self.run_all_btn.setFixedHeight(38)
        self.run_all_btn.setEnabled(False)
        self.run_all_btn.setToolTip("Run the full pipeline after project setup")
        run_all_layout.addWidget(self.run_all_btn)

        sidebar_layout.addWidget(run_all_frame)
        root.addWidget(sidebar)

        # ── Content Area ────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentArea")

        self.tab_setup = SetupTab(self.pm)
        self.tab_calib = CalibrationTab(self.pm)
        self.tab_pose2d = Pose2DTab(self.pm)
        self.tab_sync = SyncTab(self.pm)
        self.tab_triang = TriangulationTab(self.pm)
        self.tab_filter = FilteringTab(self.pm)
        self.tab_viz = VisualizationTab(self.pm)

        self.tab_setup.project_created.connect(self._on_project_created)

        for tab in [self.tab_setup, self.tab_calib, self.tab_pose2d,
                    self.tab_sync, self.tab_triang, self.tab_filter, self.tab_viz]:
            self.stack.addWidget(tab)

        root.addWidget(self.stack)

    def _build_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Welcome to Markerless — Create or open a project to begin.")

    def _go_to_step(self, idx: int):
        # Check if step is accessible
        status = self.pm.get_step_status(idx)
        if status == StepStatus.LOCKED:
            self.status_bar.showMessage(f"⚠ Complete previous steps first to unlock this step.")
            return

        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self.step_buttons):
            btn.set_active(i == idx)

        labels = [s[1] for s in STEPS]
        self.status_bar.showMessage(f"Current step: {labels[idx]}")

    def _on_project_created(self):
        cfg = self.pm.config
        self.cam_info.setText(
            f"📁 {cfg.project_name}\n"
            f"📷 {cfg.camera_count} cameras  •  {cfg.pose_estimator}"
        )
        self.cam_info.setStyleSheet("color: #58a6ff; font-size: 11px; padding: 10px 16px;")
        self.run_all_btn.setEnabled(True)

        # Persist path so we can restore it next launch
        config_path = os.path.join(cfg.project_dir, "markerless_config.json")
        self._settings.setValue("last_project_path", config_path)

        # Navigate to first step that still needs attention
        target = self._first_actionable_step()
        self.status_bar.showMessage(f"Project '{cfg.project_name}' loaded.")
        self._go_to_step(target)

    def _first_actionable_step(self) -> int:
        """Return the index of the first READY or ERROR step, or the last DONE step."""
        statuses = self.pm.config.step_status
        for i, st in enumerate(statuses):
            if StepStatus(st) in (StepStatus.READY, StepStatus.ERROR):
                return i
        # All steps are DONE (or unexpectedly all LOCKED) — go to last DONE
        for i in range(len(statuses) - 1, -1, -1):
            if StepStatus(statuses[i]) == StepStatus.DONE:
                return i
        return 0

    def _try_restore_last_project(self) -> bool:
        """Load the last project from QSettings. Returns True if successful."""
        last_path = self._settings.value("last_project_path", "")
        if not last_path or not os.path.isfile(last_path):
            return False
        try:
            self.pm.load_project(last_path)
            self._on_project_created()
            return True
        except Exception:
            # Corrupt or moved project — clear the stored path
            self._settings.remove("last_project_path")
            return False

    def _on_project_changed(self, cfg):
        for i, btn in enumerate(self.step_buttons):
            st = StepStatus(cfg.step_status[i])
            btn.set_status(st)
            btn.set_enabled_nav(st != StepStatus.LOCKED)

    def _open_project_dialog(self):
        # Start the browser in the last known project directory (if any)
        last_path = self._settings.value("last_project_path", "")
        start_dir = os.path.dirname(last_path) if last_path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project Config", start_dir, "JSON Files (*.json)"
        )
        if path:
            try:
                self.pm.load_project(path)
                self._on_project_created()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load project:\n{e}")

    def _open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    def _show_about(self):
        QMessageBox.about(self, "About Markerless",
            "<h3>Markerless</h3>"
            "<p>A PyQt5 graphical interface for the Pose2Sim 3D pose estimation pipeline.</p>"
            "<p><b>Pipeline Steps:</b></p>"
            "<ul>"
            "<li>Camera Calibration (intrinsic + extrinsic)</li>"
            "<li>2D Pose Estimation (RTMLib / OpenPose)</li>"
            "<li>Multi-camera Synchronization</li>"
            "<li>3D Triangulation</li>"
            "<li>Trajectory Filtering</li>"
            "<li>3D Marker Visualization</li>"
            "</ul>"
            "<p>Based on <a href='https://github.com/perfanalytics/pose2sim'>Pose2Sim</a> by David Pagnon.</p>"
        )

    def closeEvent(self, event):
        if self.pm.config.project_name:
            reply = QMessageBox.question(
                self, "Save Project?",
                "Save project before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if reply == QMessageBox.Save:
                self.pm.save_project()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
