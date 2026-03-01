"""
ui/main_window.py - Main application window with sidebar navigation
"""

import os
import re
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QAction,
    QFileDialog, QMessageBox, QStatusBar, QFrame,
    QSizePolicy, QApplication
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
        self.status_lbl.setStyleSheet(f"color: {color};")

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
    DEFAULT_FONT_SIZE = 13
    MIN_FONT_SIZE = 9
    MAX_FONT_SIZE = 22

    def __init__(self):
        super().__init__()
        self.pm = ProjectManager()
        self._settings = QSettings("PerfAnalytics", "Markerless")
        self.setWindowTitle("Markerless")
        self.setMinimumSize(1100, 750)
        self.resize(1280, 800)

        self._qss_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "style.qss"
        )

        settings = QSettings("PerfAnalytics", "Markerless")
        self._font_size = settings.value("font_size", self.DEFAULT_FONT_SIZE, type=int)

        self._build_menu()
        self._build_ui()
        self._build_status_bar()

        self._apply_font_size(self._font_size, save=False)

        self.pm.register_change_callback(self._on_project_changed)

        # Start on Setup tab, then try to restore last project
        self._go_to_step(0)
        self._try_restore_last_project()

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

        view_menu = menubar.addMenu("View")
        self._build_view_menu(view_menu)

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
        self.sidebar = QWidget()
        sidebar = self.sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(16, 20, 16, 16)

        self.logo_lbl = QLabel("POSE2SIM")
        self.logo_lbl.setStyleSheet("color: #58a6ff; font-size: 16px; font-weight: bold; letter-spacing: 2px;")
        logo_layout.addWidget(self.logo_lbl)

        self.sub_lbl = QLabel("3D Pose Pipeline GUI")
        self.sub_lbl.setStyleSheet("color: #8b949e; font-size: 10px;")
        logo_layout.addWidget(self.sub_lbl)

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

    def _build_view_menu(self, view_menu):
        increase_act = QAction("Increase Font Size", self)
        increase_act.setShortcut("Ctrl+=")
        increase_act.triggered.connect(lambda: self._apply_font_size(self._font_size + 1))
        view_menu.addAction(increase_act)

        decrease_act = QAction("Decrease Font Size", self)
        decrease_act.setShortcut("Ctrl+-")
        decrease_act.triggered.connect(lambda: self._apply_font_size(self._font_size - 1))
        view_menu.addAction(decrease_act)

        reset_act = QAction("Reset Font Size", self)
        reset_act.setShortcut("Ctrl+0")
        reset_act.triggered.connect(lambda: self._apply_font_size(self.DEFAULT_FONT_SIZE))
        view_menu.addAction(reset_act)

        view_menu.addSeparator()

        presets_menu = view_menu.addMenu("Font Size Presets")
        for label, size in [
            ("Small  (11px)",      11),
            ("Medium (13px)",      13),
            ("Large  (15px)",      15),
            ("Extra Large (18px)", 18),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda checked, s=size: self._apply_font_size(s))
            presets_menu.addAction(act)

    def _apply_font_size(self, size: int, save: bool = True):
        size = max(self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, size))
        self._font_size = size

        with open(self._qss_path, "r") as f:
            qss = f.read()

        def scale(m):
            orig = int(m.group(1))
            scaled = max(8, round(orig * size / self.DEFAULT_FONT_SIZE))
            return f"font-size: {scaled}px"

        QApplication.instance().setStyleSheet(
            re.sub(r"font-size:\s*(\d+)px", scale, qss)
        )

        self._update_inline_font_sizes(size)

        if save:
            QSettings("PerfAnalytics", "Markerless").setValue("font_size", size)
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage(f"Font size: {size}px", 2000)

    def _update_inline_font_sizes(self, size: int):
        ratio = size / self.DEFAULT_FONT_SIZE
        if hasattr(self, "logo_lbl"):
            s = max(8, round(16 * ratio))
            self.logo_lbl.setStyleSheet(
                f"color: #58a6ff; font-size: {s}px; font-weight: bold; letter-spacing: 2px;"
            )
        if hasattr(self, "sub_lbl"):
            s = max(8, round(10 * ratio))
            self.sub_lbl.setStyleSheet(f"color: #8b949e; font-size: {s}px;")
        if hasattr(self, "cam_info"):
            s = max(8, round(11 * ratio))
            color = "#58a6ff" if self.pm.config.project_name else "#8b949e"
            self.cam_info.setStyleSheet(
                f"color: {color}; font-size: {s}px; padding: 10px 16px;"
            )
        # Scale sidebar width and step button heights with font size
        if hasattr(self, "sidebar"):
            self.sidebar.setFixedWidth(max(180, round(220 * ratio)))
        if hasattr(self, "step_buttons"):
            for btn in self.step_buttons:
                btn.setFixedHeight(max(36, round(44 * ratio)))

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
        cam_size = max(8, round(11 * self._font_size / self.DEFAULT_FONT_SIZE))
        self.cam_info.setStyleSheet(f"color: #58a6ff; font-size: {cam_size}px; padding: 10px 16px;")
        self.run_all_btn.setEnabled(True)
        self.status_bar.showMessage(f"Project '{cfg.project_name}' loaded — proceed to Calibration.")
        # Save as last project for auto-restore on next launch
        QSettings("PerfAnalytics", "Markerless").setValue("last_project_dir", cfg.project_dir)
        # Go to calibration
        self._go_to_step(1)

    def _try_restore_last_project(self):
        """On startup, silently re-open the last used project if it still exists."""
        settings = QSettings("PerfAnalytics", "Markerless")
        last_dir = settings.value("last_project_dir", "")
        if not last_dir or not os.path.isdir(last_dir):
            return
        config_path = os.path.join(last_dir, "markerless_config.json")
        if not os.path.exists(config_path):
            return
        try:
            self.pm.load_project(config_path)
            self._on_project_created()
            self.status_bar.showMessage(
                f"Restored last project: {self.pm.config.project_name}"
            )
        except Exception:
            pass  # If restore fails, start fresh silently

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
