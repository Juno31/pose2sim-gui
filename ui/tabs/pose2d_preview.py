"""
ui/tabs/pose2d_preview.py - 2D Pose Preview

Provides two public classes:
  PosePreviewWidget  – embeddable QWidget for inline use inside a tab splitter
  PosePreviewDialog  – thin QDialog wrapper kept for backward compatibility
"""

import os
import json
import glob

from PyQt5.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QComboBox, QScrollArea, QSizePolicy, QFrame,
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# ---------------------------------------------------------------------------
# Skeleton definitions
# ---------------------------------------------------------------------------

# COCO 17-keypoint body (RTMLib "body" model)
COCO17_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),       # head
    (5, 7), (7, 9),                         # left arm
    (6, 8), (8, 10),                        # right arm
    (5, 6),                                 # shoulders
    (5, 11), (6, 12),                       # torso sides
    (11, 12),                               # hips
    (11, 13), (13, 15),                     # left leg
    (12, 14), (14, 16),                     # right leg
]

# HALPE 26-keypoint (RTMLib wholebody / Pose2Sim default)
HALPE26_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),       # head
    (5, 7), (7, 9),                         # left arm
    (6, 8), (8, 10),                        # right arm
    (5, 6),                                 # shoulders
    (5, 11), (6, 12),                       # torso sides
    (11, 12),                               # hips
    (11, 13), (13, 15), (15, 19), (15, 20), # left leg + foot
    (12, 14), (14, 16), (16, 22), (16, 23), # right leg + foot
    (19, 21), (22, 24),                     # toe tips
    (15, 17), (16, 18),                     # ankles to heels
]

# OpenPose BODY_25
BODY25_SKELETON = [
    (1, 0),
    (1, 2), (2, 3), (3, 4),
    (1, 5), (5, 6), (6, 7),
    (1, 8),
    (8, 9), (9, 10), (10, 11),
    (8, 12), (12, 13), (13, 14),
    (0, 15), (15, 17),
    (0, 16), (16, 18),
    (11, 22), (22, 23), (11, 24),
    (14, 19), (19, 20), (14, 21),
]

SKELETON_COLOR = QColor(0, 210, 110)   # bright green

_DOT_PALETTE = [
    QColor(255, 80,  80),
    QColor(255, 165,  0),
    QColor(255, 230,  0),
    QColor(130, 255,  0),
    QColor(  0, 230, 120),
    QColor(  0, 200, 255),
    QColor( 50, 100, 255),
    QColor(160,   0, 255),
    QColor(255,   0, 180),
]


def _skeleton_for(n_kps: int):
    if n_kps == 17:
        return COCO17_SKELETON
    if n_kps == 25:
        return BODY25_SKELETON
    if n_kps == 26:
        return HALPE26_SKELETON
    return []


# ---------------------------------------------------------------------------
# Camera cell widget
# ---------------------------------------------------------------------------

class _CamCell(QFrame):
    """Single camera view: title + image label."""

    def __init__(self, cam_name: str, parent=None):
        super().__init__(parent)
        self.cam_name = cam_name
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("background: #010409; border: 1px solid #30363d;")
        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        title = QLabel(cam_name.upper())
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #8b949e; font-size: 10px; border: none;")
        layout.addWidget(title)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.img_label.setStyleSheet("border: none; color: #8b949e; font-size: 11px;")
        self.img_label.setMinimumHeight(160)
        layout.addWidget(self.img_label, 1)

        self._blank()

    def _blank(self):
        self.img_label.setText("no data")

    def show_pixmap(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            self.img_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.img_label.setPixmap(scaled)


# ---------------------------------------------------------------------------
# Embeddable widget
# ---------------------------------------------------------------------------

class PosePreviewWidget(QWidget):
    """
    Inline multi-camera 2D pose visualizer.

    Usage:
        widget = PosePreviewWidget(parent)
        widget.load(project_dir, camera_count)   # call after estimation
        widget.cleanup()                          # release VideoCapture objects
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cam_data = {}     # cam_name -> {json_files, cap, frame_count}
        self._cells = {}        # cam_name -> _CamCell
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._redraw_current)
        self._current_frame = 0
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(6)

        # ── top bar ──────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        title = QLabel("2D Pose Preview")
        title.setStyleSheet("color: #c9d1d9; font-weight: bold; font-size: 13px;")
        top.addWidget(title)
        top.addStretch()

        if not HAS_CV2:
            warn = QLabel("opencv not found — video frames unavailable")
            warn.setStyleSheet("color: #e3b341; font-size: 11px;")
            top.addWidget(warn)

        self.frame_label = QLabel("Frame: — / —")
        self.frame_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        top.addWidget(self.frame_label)

        root.addLayout(top)

        # ── camera cells (horizontal scroll) ─────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll.setMinimumHeight(200)

        self.cells_container = QWidget()
        self.cells_layout = QHBoxLayout(self.cells_container)
        self.cells_layout.setContentsMargins(0, 0, 0, 0)
        self.cells_layout.setSpacing(8)

        self._placeholder = QLabel(
            "Run 2D Pose Estimation to see results here."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color: #484f58; font-size: 12px;")
        self.cells_layout.addWidget(self._placeholder)

        scroll.setWidget(self.cells_container)
        root.addWidget(scroll, 1)

        # ── slider ───────────────────────────────────────────────────
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        root.addWidget(self.slider)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, project_dir: str, camera_count: int):
        """Scan pose_2D/ and open VideoCapture objects for each camera."""
        self.cleanup()

        pose2d_dir = os.path.join(project_dir, "pose_2D")
        if not os.path.isdir(pose2d_dir):
            return

        # Remove placeholder
        self._placeholder.setParent(None)

        max_frames = 0

        for i in range(1, camera_count + 1):
            cam_name = f"cam{i:02d}"

            # Locate JSON directory
            json_dir = os.path.join(pose2d_dir, f"{cam_name}_json")
            if not os.path.isdir(json_dir):
                candidates = [
                    m for m in glob.glob(os.path.join(pose2d_dir, f"*{cam_name}*"))
                    if os.path.isdir(m)
                ]
                json_dir = candidates[0] if candidates else None

            if not json_dir:
                continue

            json_files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
            if not json_files:
                continue

            # Open VideoCapture for the flat video file
            cap = None
            if HAS_CV2:
                video_path = os.path.join(project_dir, "videos", f"{cam_name}.mp4")
                if os.path.isfile(video_path):
                    cap = cv2.VideoCapture(video_path)
                    if not cap.isOpened():
                        cap = None

            self._cam_data[cam_name] = {
                "json_files": json_files,
                "cap": cap,
                "frame_count": len(json_files),
            }

            # Build camera cell
            cell = _CamCell(cam_name)
            self._cells[cam_name] = cell
            self.cells_layout.addWidget(cell)

            max_frames = max(max_frames, len(json_files))

        if not self._cam_data:
            # Re-attach placeholder
            self.cells_layout.addWidget(self._placeholder)
            self._placeholder.show()
            return

        self.slider.setMaximum(max(0, max_frames - 1))
        self.slider.setValue(0)
        self.slider.setEnabled(True)
        self._current_frame = 0
        self._load_frame(0)

    def cleanup(self):
        """Release all VideoCapture resources."""
        for data in self._cam_data.values():
            cap = data.get("cap")
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

        for cell in self._cells.values():
            cell.setParent(None)

        self._cam_data.clear()
        self._cells.clear()
        self._current_frame = 0
        self.slider.setEnabled(False)
        self.slider.setValue(0)
        self.frame_label.setText("Frame: — / —")

        # Show placeholder again
        if self._placeholder.parent() is None:
            self.cells_layout.addWidget(self._placeholder)
        self._placeholder.show()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_slider_moved(self, value: int):
        self._current_frame = value
        total = max(d["frame_count"] for d in self._cam_data.values()) if self._cam_data else 0
        self.frame_label.setText(f"Frame: {value} / {total}")
        self._load_frame(value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(80)

    def _redraw_current(self):
        if self._cam_data:
            self._load_frame(self._current_frame)

    # ------------------------------------------------------------------
    # Frame rendering
    # ------------------------------------------------------------------

    def _load_frame(self, frame_idx: int):
        if not self._cam_data:
            return

        total = max(d["frame_count"] for d in self._cam_data.values())
        self.frame_label.setText(f"Frame: {frame_idx} / {total}")

        for cam_name, data in self._cam_data.items():
            cell = self._cells.get(cam_name)
            if cell is None:
                continue

            json_files = data["json_files"]
            cap = data["cap"]
            n = data["frame_count"]

            if frame_idx >= n:
                continue

            # Parse keypoints
            keypoints = []
            try:
                with open(json_files[frame_idx], "r") as fh:
                    pose_data = json.load(fh)
                people = pose_data.get("people", [])
                if people:
                    flat = people[0].get("pose_keypoints_2d", [])
                    keypoints = [
                        (flat[j], flat[j + 1], flat[j + 2])
                        for j in range(0, len(flat) - 2, 3)
                    ]
            except Exception:
                pass

            # Get video frame
            pixmap = None
            if cap is not None:
                try:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = cap.read()
                    if ret:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        h, w, ch = frame_rgb.shape
                        img = QImage(
                            frame_rgb.data, w, h, ch * w, QImage.Format_RGB888
                        ).copy()
                        pixmap = QPixmap.fromImage(img)
                except Exception:
                    pass

            if pixmap is None:
                pixmap = QPixmap(960, 540)
                pixmap.fill(QColor(22, 27, 34))

            if keypoints:
                pixmap = _draw_pose(pixmap, keypoints)

            cell.show_pixmap(pixmap)


# ---------------------------------------------------------------------------
# Drawing helper
# ---------------------------------------------------------------------------

def _draw_pose(pixmap: QPixmap, keypoints: list) -> QPixmap:
    result = QPixmap(pixmap)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)

    conf_threshold = 0.3
    kp_radius = max(4, pixmap.width() // 180)
    line_width = max(2, pixmap.width() // 300)
    skeleton = _skeleton_for(len(keypoints))

    pen = QPen(SKELETON_COLOR, line_width)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    for a, b in skeleton:
        if a < len(keypoints) and b < len(keypoints):
            xa, ya, ca = keypoints[a]
            xb, yb, cb = keypoints[b]
            if ca > conf_threshold and cb > conf_threshold:
                painter.drawLine(int(xa), int(ya), int(xb), int(yb))

    for idx, (x, y, conf) in enumerate(keypoints):
        if conf < conf_threshold:
            continue
        color = _DOT_PALETTE[idx % len(_DOT_PALETTE)]
        painter.setPen(QPen(QColor(0, 0, 0, 160), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(
            int(x) - kp_radius, int(y) - kp_radius,
            kp_radius * 2, kp_radius * 2,
        )

    painter.end()
    return result


# ---------------------------------------------------------------------------
# Dialog wrapper (backward compatibility)
# ---------------------------------------------------------------------------

class PosePreviewDialog(QDialog):
    """QDialog wrapper around PosePreviewWidget."""

    def __init__(self, project_dir: str, camera_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("2D Pose Preview")
        self.resize(1100, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._widget = PosePreviewWidget(self)
        layout.addWidget(self._widget, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._widget.load(project_dir, camera_count)

    def closeEvent(self, event):
        self._widget.cleanup()
        super().closeEvent(event)
