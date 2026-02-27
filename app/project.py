"""
core/project.py - Manages the global project state and configuration
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from enum import IntEnum


class StepStatus(IntEnum):
    LOCKED = 0
    READY = 1
    RUNNING = 2
    DONE = 3
    ERROR = 4


@dataclass
class ProjectConfig:
    # Project basics
    project_dir: str = ""
    project_name: str = ""

    # Camera settings
    camera_count: int = 2  # 2, 3, or 4

    # Pose estimator
    pose_estimator: str = "RTMLib"  # "RTMLib" or "OpenPose"
    rtmlib_model: str = "body"  # body, wholebody, hand, face
    openpose_path: str = ""

    # Calibration
    calib_intrinsic_type: str = "checkerboard"  # checkerboard, charuco, None
    calib_extrinsic_type: str = "scene"  # scene, board
    checkerboard_cols: int = 6
    checkerboard_rows: int = 9
    square_size_mm: float = 40.0
    calib_video_dirs: List[str] = field(default_factory=list)
    calib_scene_file: str = ""

    # 2D Pose Estimation
    pose_video_dirs: List[str] = field(default_factory=list)
    pose_overwrite: bool = False

    # Synchronization
    sync_display: bool = True
    sync_approx_time_maxspeed: float = 0.5
    sync_filter_cutoff: float = 6.0
    sync_filter_order: int = 4

    # Triangulation
    triang_reproj_error_threshold: float = 15.0
    triang_min_cameras: int = 2
    triang_interpolate_missing: bool = True
    triang_interp_if_gap_smaller_than: int = 10
    triang_show_reprojection: bool = False

    # Filtering
    filter_type: str = "butterworth"  # butterworth, kalman, gaussian, LOESS, median
    filter_cutoff: float = 6.0
    filter_order: int = 4
    filter_display: bool = False

    # Visualization
    viz_marker_size: int = 15
    viz_line_width: int = 3
    viz_save_video: bool = True
    viz_show_axes: bool = True

    # Step completion status
    step_status: List[int] = field(default_factory=lambda: [
        StepStatus.READY,    # 0: Setup
        StepStatus.LOCKED,   # 1: Calibration
        StepStatus.LOCKED,   # 2: 2D Pose
        StepStatus.LOCKED,   # 3: Synchronization
        StepStatus.LOCKED,   # 4: Triangulation
        StepStatus.LOCKED,   # 5: Filtering
        StepStatus.LOCKED,   # 6: Visualization
    ])

    def to_dict(self):
        return asdict(self)

    def save(self, path: Optional[str] = None):
        save_path = path or os.path.join(self.project_dir, "markerless_config.json")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ProjectConfig":
        with open(path, "r") as f:
            data = json.load(f)
        cfg = cls()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


class ProjectManager:
    """Singleton-like manager for the current project state."""

    def __init__(self):
        self.config = ProjectConfig()
        self._callbacks = []

    def register_change_callback(self, cb):
        self._callbacks.append(cb)

    def notify(self):
        for cb in self._callbacks:
            cb(self.config)

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        self.notify()

    def set_step_status(self, step_idx: int, status: StepStatus):
        self.config.step_status[step_idx] = int(status)
        # Unlock next step if done
        if status == StepStatus.DONE and step_idx + 1 < len(self.config.step_status):
            if self.config.step_status[step_idx + 1] == StepStatus.LOCKED:
                self.config.step_status[step_idx + 1] = StepStatus.READY
        # Persist immediately so status survives app restarts
        if self.config.project_dir:
            try:
                self.config.save()
            except Exception:
                pass
        self.notify()

    def get_step_status(self, step_idx: int) -> StepStatus:
        return StepStatus(self.config.step_status[step_idx])

    def save_project(self):
        if self.config.project_dir:
            self.config.save()

    def load_project(self, path: str):
        self.config = ProjectConfig.load(path)
        self.notify()

    def new_project(self, project_dir: str, project_name: str, camera_count: int, pose_estimator: str):
        self.config = ProjectConfig(
            project_dir=project_dir,
            project_name=project_name,
            camera_count=camera_count,
            pose_estimator=pose_estimator,
        )
        os.makedirs(project_dir, exist_ok=True)
        self.notify()
