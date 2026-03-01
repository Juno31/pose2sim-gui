"""
ui/tabs/tab_visualization.py - 3D Visualization Tab with embedded TRC viewer
"""

import os
import glob
import sys
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QSpinBox, QCheckBox, QSplitter, QPushButton, QSlider, QComboBox,
    QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QTimer

from ui.components.widgets import StepRunWidget
from app.project import ProjectManager, StepStatus
from app.runner import ScriptWorker

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib
    matplotlib.use("Qt5Agg")
    _MPL_OK = True
except ImportError:
    _MPL_OK = False

try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    from PyQt5.QtCore import QUrl
    _MEDIA_OK = True
except ImportError:
    _MEDIA_OK = False

# ── Skeleton connections (HALPE_26 / Body_with_feet) ─────────────────────────
SKELETON_CONNECTIONS = [
    ("Hip", "Neck"),
    ("Hip", "RHip"), ("RHip", "RKnee"), ("RKnee", "RAnkle"),
    ("RAnkle", "RBigToe"), ("RAnkle", "RHeel"), ("RAnkle", "RSmallToe"),
    ("Hip", "LHip"), ("LHip", "LKnee"), ("LKnee", "LAnkle"),
    ("LAnkle", "LBigToe"), ("LAnkle", "LHeel"), ("LAnkle", "LSmallToe"),
    ("Neck", "Head"), ("Head", "Nose"),
    ("Neck", "RShoulder"), ("RShoulder", "RElbow"), ("RElbow", "RWrist"),
    ("Neck", "LShoulder"), ("LShoulder", "LElbow"), ("LElbow", "LWrist"),
]


# ── TRC parser ────────────────────────────────────────────────────────────────
def parse_trc(path: str):
    """
    Parse a .trc file.
    Returns (marker_names, data, frame_rate, units).
    data shape: (n_frames, 2 + n_markers*3)  columns: [frame, time, x0,y0,z0, x1,y1,z1, ...]
    """
    with open(path, "r") as f:
        lines = f.readlines()

    # Row 3 (index 2): metadata values
    meta = lines[2].strip().split("\t")
    frame_rate = float(meta[0]) if meta[0] else 30.0
    units      = meta[4] if len(meta) > 4 else "m"

    # Row 4 (index 3): marker names (empty cells are Y/Z of previous marker)
    headers = lines[3].strip().split("\t")
    marker_names = [h.strip() for h in headers[2:] if h.strip()]

    # Data starts at row 6 (index 5)
    rows = []
    for line in lines[5:]:
        parts = line.strip().split("\t")
        if not parts or not parts[0].strip():
            continue
        row = []
        for p in parts:
            try:
                row.append(float(p) if p.strip() else float("nan"))
            except ValueError:
                row.append(float("nan"))
        if len(row) >= 2:
            rows.append(row)

    # Pad rows to the same length
    max_len = max(len(r) for r in rows) if rows else 0
    for r in rows:
        r.extend([float("nan")] * (max_len - len(r)))

    data = np.array(rows, dtype=float)
    return marker_names, data, frame_rate, units


# ── Matplotlib 3D canvas ──────────────────────────────────────────────────────
if _MPL_OK:
    class SkeletonCanvas(FigureCanvasQTAgg):
        def __init__(self, parent=None):
            self.fig = Figure(facecolor="#0d1117")
            super().__init__(self.fig)
            self.setParent(parent)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.ax = self.fig.add_subplot(111, projection="3d")
            self._marker_names = []
            self._data = None
            self._n_frames = 0
            self._xlim = (-2, 2)
            self._ylim = (-2, 2)
            self._zlim = (-2, 2)
            self._style_axes()
            self._draw_placeholder()

        def _style_axes(self):
            ax = self.ax
            ax.set_facecolor("#0d1117")
            self.fig.patch.set_facecolor("#0d1117")
            for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
                pane.fill = False
                pane.set_edgecolor("#21262d")
            ax.tick_params(colors="#8b949e", labelsize=7)
            ax.xaxis.label.set_color("#8b949e")
            ax.yaxis.label.set_color("#8b949e")
            ax.zaxis.label.set_color("#8b949e")
            try:
                ax.xaxis._axinfo["grid"]["color"] = "#21262d"
                ax.yaxis._axinfo["grid"]["color"] = "#21262d"
                ax.zaxis._axinfo["grid"]["color"] = "#21262d"
            except Exception:
                pass

        def _draw_placeholder(self):
            self.ax.clear()
            self._style_axes()
            self.ax.text2D(0.5, 0.5, "Load a .trc file to view",
                           transform=self.ax.transAxes,
                           ha="center", va="center",
                           color="#8b949e", fontsize=11)
            self.draw()

        def load_trc(self, marker_names, data, frame_rate):
            self._marker_names = marker_names
            self._data = data
            self._n_frames = data.shape[0]
            # Compute axis limits from all frames
            coords = data[:, 2:].reshape(data.shape[0], -1, 3)
            valid  = coords[~np.isnan(coords).any(axis=2)]
            if len(valid) > 0:
                pad = 0.2
                self._xlim = (valid[:, 0].min() - pad, valid[:, 0].max() + pad)
                self._ylim = (valid[:, 1].min() - pad, valid[:, 1].max() + pad)
                self._zlim = (valid[:, 2].min() - pad, valid[:, 2].max() + pad)
            self.draw_frame(0)

        def draw_frame(self, frame_idx: int):
            if self._data is None or frame_idx >= self._n_frames:
                return

            self.ax.clear()
            self._style_axes()

            row = self._data[frame_idx]
            positions = {}
            for i, name in enumerate(self._marker_names):
                col = 2 + i * 3
                if col + 2 < len(row):
                    x, y, z = row[col], row[col + 1], row[col + 2]
                    if not (np.isnan(x) or np.isnan(y) or np.isnan(z)):
                        positions[name] = (x, y, z)

            # Draw skeleton lines
            for a, b in SKELETON_CONNECTIONS:
                if a in positions and b in positions:
                    pa, pb = positions[a], positions[b]
                    self.ax.plot(
                        [pa[0], pb[0]], [pa[1], pb[1]], [pa[2], pb[2]],
                        "-", color="#58a6ff", linewidth=1.8, alpha=0.85,
                    )

            # Draw joints
            if positions:
                xs = [p[0] for p in positions.values()]
                ys = [p[1] for p in positions.values()]
                zs = [p[2] for p in positions.values()]
                self.ax.scatter(xs, ys, zs, c="#7ee787", s=25, zorder=5,
                                depthshade=False)

            # Axis limits and labels
            self.ax.set_xlim(self._xlim)
            self.ax.set_ylim(self._ylim)
            self.ax.set_zlim(self._zlim)
            self.ax.set_xlabel("X", fontsize=8)
            self.ax.set_ylabel("Y", fontsize=8)
            self.ax.set_zlabel("Z", fontsize=8)

            time_val = row[1] if len(row) > 1 and not np.isnan(row[1]) else frame_idx
            self.ax.set_title(
                f"Frame {int(row[0])}   t = {time_val:.3f} s",
                color="#e6edf3", fontsize=9, pad=4,
            )
            self.draw()


# ── Main visualization tab ────────────────────────────────────────────────────
class VisualizationTab(QWidget):
    def __init__(self, pm: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = pm
        self.worker = None
        self._trc_data   = None
        self._trc_names  = []
        self._frame_rate = 30.0
        self._n_frames   = 0
        self._playing    = False
        self._timer      = QTimer()
        self._timer.timeout.connect(self._advance_frame)
        self._media_player = None
        self._video_path   = None
        self._build_ui()
        pm.register_change_callback(self._on_project_changed)

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        # Row 1: Title
        title = QLabel("3D Visualization")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Embedded 3D viewer for .trc skeleton files.\n"
                      "Load a file or run the pipeline to generate one.")
        desc.setObjectName("sectionDesc")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        # Vertical splitter: settings (top) / canvas (bottom)
        v_split = QSplitter(Qt.Vertical)

        # ── Row 2: Visualization Settings (full width) ────────────────────────
        settings_row = QWidget()
        settings_layout = QHBoxLayout(settings_row)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(12)

        # Settings group
        settings_group = QGroupBox("Visualization Settings")
        form = QFormLayout(settings_group)
        form.setSpacing(8)

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

        self.feet_on_floor = QCheckBox("Translate feet to floor level")
        self.feet_on_floor.setToolTip("Useful for estimating ground reaction forces (markerAugmentation)")
        form.addRow(self.feet_on_floor)

        self.make_c3d_aug = QCheckBox("Save augmented markers as .c3d")
        self.make_c3d_aug.setChecked(True)
        form.addRow(self.make_c3d_aug)

        # Save Config button for visualization settings
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("💾  Save Config")
        self.save_btn.setToolTip("Write settings to Config.toml")
        self.save_btn.clicked.connect(self._save_config)
        save_row.addWidget(self.save_btn)
        self.save_status = QLabel("")
        self.save_status.setStyleSheet("color: #7ee787;")
        save_row.addWidget(self.save_status)
        save_row.addStretch()
        form.addRow(save_row)

        settings_layout.addWidget(settings_group)

        # TRC file picker group
        trc_group = QGroupBox("TRC File")
        trc_layout = QVBoxLayout(trc_group)
        trc_layout.setSpacing(6)

        self.trc_combo = QComboBox()
        self.trc_combo.setToolTip("Select a .trc file from the project")
        trc_layout.addWidget(self.trc_combo)

        btn_row = QHBoxLayout()
        self.load_trc_btn = QPushButton("Load Selected")
        self.load_trc_btn.clicked.connect(self._load_selected_trc)
        btn_row.addWidget(self.load_trc_btn)

        self.browse_trc_btn = QPushButton("Browse…")
        self.browse_trc_btn.clicked.connect(self._browse_trc)
        btn_row.addWidget(self.browse_trc_btn)
        trc_layout.addLayout(btn_row)

        self.trc_info = QLabel("No file loaded")
        self.trc_info.setStyleSheet("color: #8b949e;")
        self.trc_info.setWordWrap(True)
        trc_layout.addWidget(self.trc_info)

        settings_layout.addWidget(trc_group)

        # Run widget (fills remaining horizontal space)
        self.run_widget = StepRunWidget("Run Visualization (Pose2Sim)")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        settings_layout.addWidget(self.run_widget, stretch=1)

        v_split.addWidget(settings_row)

        # ── Row 3: Skeleton (left) + Video player (right) + shared controls ───
        canvas_section = QWidget()
        canvas_outer = QVBoxLayout(canvas_section)
        canvas_outer.setContentsMargins(0, 0, 0, 0)
        canvas_outer.setSpacing(6)

        # Horizontal splitter: 3D skeleton | video player
        h_split = QSplitter(Qt.Horizontal)

        # -- Left panel: SkeletonCanvas --
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        if _MPL_OK:
            self.canvas = SkeletonCanvas(self)
            left_layout.addWidget(self.canvas)
        else:
            no_mpl = QLabel("matplotlib not available.\n"
                            "Install it to use the 3D viewer:\n  pip install matplotlib")
            no_mpl.setAlignment(Qt.AlignCenter)
            no_mpl.setStyleSheet("color: #8b949e;")
            left_layout.addWidget(no_mpl)

        h_split.addWidget(left_panel)

        # -- Right panel: Video player --
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        if _MEDIA_OK:
            self._video_widget = QVideoWidget()
            self._video_widget.setStyleSheet("background: #0d1117;")
            self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
            self._media_player.setVideoOutput(self._video_widget)
            self._media_player.setMuted(True)
            right_layout.addWidget(self._video_widget)
        else:
            no_media = QLabel("PyQt5.QtMultimedia not available.\n"
                              "Install it to enable video playback.")
            no_media.setAlignment(Qt.AlignCenter)
            no_media.setStyleSheet("color: #8b949e;")
            right_layout.addWidget(no_media)

        # Video file picker
        vid_picker_frame = QFrame()
        vid_picker_frame.setStyleSheet(
            "QFrame { background: #161b22; border-radius: 4px; }"
        )
        vid_picker_layout = QHBoxLayout(vid_picker_frame)
        vid_picker_layout.setContentsMargins(6, 4, 6, 4)
        vid_picker_layout.setSpacing(6)

        self.video_combo = QComboBox()
        self.video_combo.setToolTip("Select a video file from the project")
        vid_picker_layout.addWidget(self.video_combo, stretch=1)

        self.load_video_btn = QPushButton("Load")
        self.load_video_btn.setEnabled(False)
        self.load_video_btn.clicked.connect(self._load_selected_video)
        vid_picker_layout.addWidget(self.load_video_btn)

        self.browse_video_btn = QPushButton("Browse…")
        self.browse_video_btn.clicked.connect(self._browse_video)
        vid_picker_layout.addWidget(self.browse_video_btn)

        right_layout.addWidget(vid_picker_frame)
        h_split.addWidget(right_panel)

        h_split.setStretchFactor(0, 1)
        h_split.setStretchFactor(1, 1)

        canvas_outer.addWidget(h_split, stretch=1)

        # Shared playback controls (slider + buttons) below both panels
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("QFrame { background: #161b22; border-radius: 6px; padding: 4px; }")
        ctrl_layout = QVBoxLayout(ctrl_frame)
        ctrl_layout.setContentsMargins(8, 6, 8, 6)
        ctrl_layout.setSpacing(6)

        # Slider
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.setValue(0)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        ctrl_layout.addWidget(self.frame_slider)

        # Buttons + info row
        btn_row2 = QHBoxLayout()

        self.first_btn = QPushButton("⏮")
        self.first_btn.setEnabled(False)
        self.first_btn.clicked.connect(self._goto_first)
        btn_row2.addWidget(self.first_btn)

        self.prev_btn = QPushButton("|◀")
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._prev_frame)
        btn_row2.addWidget(self.prev_btn)

        self.play_btn = QPushButton("▶")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._toggle_play)
        btn_row2.addWidget(self.play_btn)

        self.next_btn = QPushButton("▶|")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self._next_frame_btn)
        btn_row2.addWidget(self.next_btn)

        self.last_btn = QPushButton("⏭")
        self.last_btn.setEnabled(False)
        self.last_btn.clicked.connect(self._goto_last)
        btn_row2.addWidget(self.last_btn)

        btn_row2.addSpacing(16)

        speed_lbl = QLabel("Speed:")
        speed_lbl.setStyleSheet("color: #8b949e;")
        btn_row2.addWidget(speed_lbl)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25×", "0.5×", "1×", "2×", "4×"])
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        btn_row2.addWidget(self.speed_combo)

        btn_row2.addStretch()

        self.frame_label = QLabel("– / –")
        self.frame_label.setStyleSheet("color: #8b949e;")
        btn_row2.addWidget(self.frame_label)

        ctrl_layout.addLayout(btn_row2)
        canvas_outer.addWidget(ctrl_frame)

        v_split.addWidget(canvas_section)

        # Settings row gets a fixed share; canvas expands
        v_split.setStretchFactor(0, 0)
        v_split.setStretchFactor(1, 1)
        v_split.setSizes([260, 540])

        outer.addWidget(v_split)

    # ── TRC loading ───────────────────────────────────────────────────────────
    def _scan_trc_files(self, project_dir: str):
        """Find all .trc files in the project directory."""
        files = glob.glob(os.path.join(project_dir, "**", "*.trc"), recursive=True)
        # Prioritise filtered/augmented files, then raw pose-3d
        files.sort(key=lambda p: (
            0 if "LSTM" in p else
            1 if "filt" in p else
            2 if "calibration" not in p else 3
        ))
        return files

    def _populate_trc_combo(self, project_dir: str):
        self.trc_combo.clear()
        files = self._scan_trc_files(project_dir)
        for f in files:
            self.trc_combo.addItem(os.path.relpath(f, project_dir), f)
        if files:
            self.load_trc_btn.setEnabled(True)
        return files

    def _load_trc_file(self, path: str):
        if not os.path.exists(path):
            self.trc_info.setText(f"File not found:\n{path}")
            return
        try:
            names, data, fps, units = parse_trc(path)
        except Exception as e:
            self.trc_info.setText(f"Parse error: {e}")
            return

        self._trc_data   = data
        self._trc_names  = names
        self._frame_rate = fps
        self._n_frames   = data.shape[0]

        self.trc_info.setText(
            f"{os.path.basename(path)}\n"
            f"{len(names)} markers  ·  {self._n_frames} frames  ·  {fps:.1f} fps  ·  {units}"
        )
        self.trc_info.setStyleSheet("color: #58a6ff;")

        # Update slider
        self.frame_slider.setRange(0, max(0, self._n_frames - 1))
        self.frame_slider.setValue(0)
        self.frame_slider.setEnabled(True)

        # Enable controls
        for btn in (self.first_btn, self.prev_btn, self.play_btn,
                    self.next_btn, self.last_btn):
            btn.setEnabled(True)

        self._update_frame_label(0)
        self._update_speed()

        if _MPL_OK:
            self.canvas.load_trc(names, data, fps)

    def _load_selected_trc(self):
        path = self.trc_combo.currentData()
        if path:
            self._load_trc_file(path)

    def _browse_trc(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open TRC file", "", "TRC Files (*.trc);;All Files (*)"
        )
        if path:
            self._load_trc_file(path)

    # ── Video file management ──────────────────────────────────────────────────
    def _scan_video_files(self, project_dir: str):
        patterns = ["*.mp4", "*.avi", "*.mov", "*.mkv"]
        files = []
        for pat in patterns:
            files.extend(glob.glob(os.path.join(project_dir, "**", pat), recursive=True))
        files.sort()
        return files

    def _populate_video_combo(self, project_dir: str):
        self.video_combo.clear()
        files = self._scan_video_files(project_dir)
        for f in files:
            self.video_combo.addItem(os.path.relpath(f, project_dir), f)
        self.load_video_btn.setEnabled(bool(files))
        return files

    def _load_video_file(self, path: str):
        if not _MEDIA_OK or self._media_player is None:
            return
        if not os.path.exists(path):
            return
        self._video_path = path
        url = QUrl.fromLocalFile(os.path.abspath(path))
        self._media_player.setMedia(QMediaContent(url))
        self._media_player.pause()
        self._seek_video(self._current_frame())

    def _load_selected_video(self):
        path = self.video_combo.currentData()
        if path:
            self._load_video_file(path)

    def _browse_video(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open video file", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)"
        )
        if path:
            self._load_video_file(path)

    # ── Playback controls ─────────────────────────────────────────────────────
    def _current_frame(self) -> int:
        return self.frame_slider.value()

    def _goto_frame(self, idx: int):
        idx = max(0, min(idx, self._n_frames - 1))
        self.frame_slider.setValue(idx)

    def _on_slider_changed(self, idx: int):
        self._update_frame_label(idx)
        if _MPL_OK and self._trc_data is not None:
            self.canvas.draw_frame(idx)
        self._seek_video(idx)

    def _seek_video(self, frame_idx: int):
        if self._media_player is None or not _MEDIA_OK or not self._video_path:
            return
        ms = int(frame_idx / max(self._frame_rate, 1) * 1000)
        self._media_player.setPosition(ms)

    def _update_frame_label(self, idx: int):
        if self._n_frames > 0 and self._trc_data is not None:
            row = self._trc_data[idx]
            t = row[1] if not np.isnan(row[1]) else idx / max(self._frame_rate, 1)
            self.frame_label.setText(f"Frame {idx + 1} / {self._n_frames}  |  {t:.3f} s")
        else:
            self.frame_label.setText("– / –")

    def _goto_first(self):
        self._stop_play()
        self._goto_frame(0)

    def _goto_last(self):
        self._stop_play()
        self._goto_frame(self._n_frames - 1)

    def _prev_frame(self):
        self._stop_play()
        self._goto_frame(self._current_frame() - 1)

    def _next_frame_btn(self):
        self._stop_play()
        self._goto_frame(self._current_frame() + 1)

    def _advance_frame(self):
        nxt = self._current_frame() + 1
        if nxt >= self._n_frames:
            nxt = 0  # loop
        self._goto_frame(nxt)

    def _toggle_play(self):
        if self._playing:
            self._stop_play()
        else:
            self._start_play()

    def _start_play(self):
        self._playing = True
        self.play_btn.setText("⏸")
        self._update_speed()
        self._timer.start()

    def _stop_play(self):
        self._playing = False
        self.play_btn.setText("▶")
        self._timer.stop()

    def _on_speed_changed(self):
        if self._playing:
            self._update_speed()

    def _update_speed(self):
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
        speed  = speeds[self.speed_combo.currentIndex()]
        interval = int(1000.0 / max(self._frame_rate, 1) / speed)
        self._timer.setInterval(max(16, interval))  # cap at ~60 fps

    def _save_config(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.save_status.setText("✗ No project loaded")
            self.save_status.setStyleSheet("color: #f85149;")
            return
        from app.toml_bridge import save_toml_values
        save_toml_values(cfg.project_dir, [
            ("markerAugmentation", "feet_on_floor", self.feet_on_floor.isChecked()),
            ("markerAugmentation", "make_c3d",      self.make_c3d_aug.isChecked()),
        ])
        self.save_status.setText("✓ Saved")
        self.save_status.setStyleSheet("color: #7ee787;")
        QTimer.singleShot(3000, lambda: self.save_status.setText(""))

    def _load_viz_toml(self, data: dict):
        aug = data.get("markerAugmentation", {})
        val = aug.get("feet_on_floor")
        if isinstance(val, bool):
            self.feet_on_floor.setChecked(val)
        val = aug.get("make_c3d")
        if isinstance(val, bool):
            self.make_c3d_aug.setChecked(val)

    # ── Project change hook ───────────────────────────────────────────────────
    def _on_project_changed(self, cfg):
        if cfg.project_dir:
            from app.toml_bridge import load_toml
            data = load_toml(cfg.project_dir)
            if data:
                self._load_viz_toml(data)
            files = self._populate_trc_combo(cfg.project_dir)
            # Auto-load the best TRC file if found
            if files:
                self._load_trc_file(files[0])
            # Populate video combo from project video files
            self._populate_video_combo(cfg.project_dir)

    # ── Pose2Sim run ──────────────────────────────────────────────────────────
    def _run(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded.")
            return

        cfg.viz_marker_size = self.marker_size.value()
        cfg.viz_line_width  = self.line_width.value()
        cfg.viz_save_video  = self.save_video.isChecked()
        cfg.viz_show_axes   = self.show_axes.isChecked()

        self.run_widget.set_running(True)
        self.run_widget.log.append(
            f"[INFO] Viz | Marker: {cfg.viz_marker_size}px | "
            f"Line: {cfg.viz_line_width}px | Save video: {cfg.viz_save_video}"
        )

        cmd = [sys.executable, "-c",
               f"import os; os.chdir({repr(cfg.project_dir)}); "
               f"from Pose2Sim import Pose2Sim; Pose2Sim.markerAugmentation()"]
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
            self.pm.set_step_status(6, StepStatus.DONE)
            # Refresh TRC list after pipeline completes
            cfg = self.pm.config
            if cfg.project_dir:
                files = self._populate_trc_combo(cfg.project_dir)
                if files:
                    self._load_trc_file(files[0])
