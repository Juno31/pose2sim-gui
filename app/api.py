"""
app/api.py - Python API exposed to JavaScript via pywebview.
Every public method is callable from JS as: await window.pywebview.api.method_name(...)
"""

import os
import sys
import json
import glob
import shutil
import base64
import subprocess
import threading
import traceback

import cv2
import numpy as np

from app.project import ProjectManager, ProjectConfig, StepStatus
from app.toml_bridge import load_toml, save_toml_values


class Api:
    _SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.app_settings.json')

    def __init__(self):
        self.pm = ProjectManager()
        self._window = None  # Set by main_web.py after window creation
        self._worker_thread = None
        self._worker_proc = None
        self._log_buffer = []
        self._log_lock = threading.Lock()
        self._running = False

    def _save_last_project(self, project_dir):
        """Remember the last opened project path."""
        try:
            settings = {}
            if os.path.exists(self._SETTINGS_FILE):
                with open(self._SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
            settings['last_project_dir'] = project_dir
            with open(self._SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass

    def get_last_project(self):
        """Return the last opened project directory, or None."""
        try:
            if os.path.exists(self._SETTINGS_FILE):
                with open(self._SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                path = settings.get('last_project_dir')
                if path and os.path.isdir(path):
                    return {"success": True, "project_dir": path}
            return {"success": False}
        except Exception:
            return {"success": False}

    # ─── Project Management ───────────────────────────────────────

    def new_project(self, project_name, project_dir, camera_count, pose_estimator):
        """Create a new Pose2Sim project with folder structure."""
        try:
            project_path = os.path.join(project_dir, project_name)
            os.makedirs(project_path, exist_ok=True)

            # Copy default Config.toml from Pose2Sim
            try:
                import Pose2Sim
                demo_dir = os.path.join(os.path.dirname(Pose2Sim.__file__), "Demo_SinglePerson")
                src_toml = os.path.join(demo_dir, "Config.toml")
                dst_toml = os.path.join(project_path, "Config.toml")
                if os.path.exists(src_toml) and not os.path.exists(dst_toml):
                    shutil.copy2(src_toml, dst_toml)
            except Exception:
                pass

            # Create camera folders
            for i in range(1, camera_count + 1):
                cam = f"cam{i:02d}"
                os.makedirs(os.path.join(project_path, "calibration", "intrinsics", f"int_{cam}_img"), exist_ok=True)
                os.makedirs(os.path.join(project_path, "calibration", "extrinsics", f"ext_{cam}_img"), exist_ok=True)
                os.makedirs(os.path.join(project_path, "videos", cam), exist_ok=True)

            self.pm.new_project(project_path, project_name, camera_count, pose_estimator)
            self.pm.set_step_status(0, StepStatus.DONE)
            self.pm.save_project()
            self._save_last_project(project_path)
            return {"success": True, "project_dir": project_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_project(self, project_dir):
        """Open an existing project by directory path."""
        try:
            config_path = os.path.join(project_dir, "markerless_config.json")
            if os.path.exists(config_path):
                self.pm.load_project(config_path)
            else:
                # Try to infer from folder structure
                name = os.path.basename(project_dir)
                cam_dirs = glob.glob(os.path.join(project_dir, "videos", "cam*"))
                cam_count = max(len(cam_dirs), 2)
                self.pm.new_project(project_dir, name, cam_count, "RTMLib")
                self.pm.set_step_status(0, StepStatus.DONE)
                self.pm.save_project()
            self._save_last_project(project_dir)
            return {"success": True, "config": self.pm.config.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_project_config(self):
        """Get current project config as dict."""
        return self.pm.config.to_dict()

    def browse_directory(self):
        """Open native folder picker dialog."""
        import webview
        if self._window:
            result = self._window.create_file_dialog(
                dialog_type=webview.FOLDER_DIALOG,
            )
            if result and len(result) > 0:
                return result[0]
        return None

    def browse_file(self, file_types=None):
        """Open native file picker dialog."""
        import webview
        if self._window:
            ft = file_types or ("All files (*.*)",)
            if isinstance(ft, str):
                ft = (ft,)
            result = self._window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                file_types=tuple(ft),
            )
            if result and len(result) > 0:
                return result[0]
        return None

    # ─── Config.toml Read/Write ───────────────────────────────────

    def load_config(self):
        """Load Config.toml and return as nested dict."""
        if not self.pm.config.project_dir:
            return {}
        return load_toml(self.pm.config.project_dir)

    def save_config(self, updates):
        """
        Save values to Config.toml.
        updates: list of [section, key, value] triples
        """
        if not self.pm.config.project_dir:
            return {"success": False, "error": "No project loaded"}
        try:
            tuples = [(u[0], u[1], u[2]) for u in updates]
            save_toml_values(self.pm.config.project_dir, tuples)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Pipeline Execution ───────────────────────────────────────

    def run_step(self, step_name):
        """
        Run a pipeline step as a subprocess.
        step_name: 'calibration', 'poseEstimation', 'synchronization',
                   'triangulation', 'filtering', 'markerAugmentation'
        """
        if self._running:
            return {"success": False, "error": "A step is already running"}
        if not self.pm.config.project_dir:
            return {"success": False, "error": "No project loaded"}

        step_map = {
            "calibration": 1,
            "poseEstimation": 2,
            "synchronization": 3,
            "triangulation": 4,
            "filtering": 5,
            "markerAugmentation": 6,
        }
        step_idx = step_map.get(step_name)
        if step_idx is None:
            return {"success": False, "error": f"Unknown step: {step_name}"}

        self._running = True
        with self._log_lock:
            self._log_buffer = []

        self.pm.set_step_status(step_idx, StepStatus.RUNNING)

        # For calibration: run intrinsics only (extrinsics handled by in-window clicker)
        if step_name == 'calibration':
            proj_dir = self.pm.config.project_dir
            script_path = os.path.join(proj_dir, '_run_intrinsics.py')
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(
                    "import os, sys, logging, traceback\n"
                    "import toml, numpy as np\n"
                    "sys.stdout.reconfigure(encoding='utf-8')\n"
                    "logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)\n"
                    f"proj_dir = {repr(proj_dir)}\n"
                    "os.chdir(proj_dir)\n"
                    "calib_dir = os.path.join(proj_dir, 'calibration')\n"
                    "try:\n"
                    "    cfg = toml.load(os.path.join(proj_dir, 'Config.toml'))\n"
                    "    intrinsics_cfg = cfg.get('calibration',{}).get('calculate',{}).get('intrinsics',{})\n"
                    "    save_debug = cfg.get('calibration',{}).get('calculate',{}).get('save_debug_images', True)\n"
                    "    intrinsics_cfg['show_detection_intrinsics'] = False\n"
                    "    intrinsics_cfg['overwrite_intrinsics'] = True\n"
                    "    from Pose2Sim.calibration import calibrate_intrinsics, toml_write\n"
                    "    ret, C, S, D, K, R, T = calibrate_intrinsics(calib_dir, intrinsics_cfg, save_debug_images=save_debug)\n"
                    "    out_path = os.path.join(calib_dir, 'Calib_intrinsics_only.toml')\n"
                    "    toml_write(out_path, C, S, D, K, R, T)\n"
                    "    logging.info(f'Intrinsic calibration saved to {out_path}')\n"
                    "    for i, cam in enumerate(C):\n"
                    "        logging.info(f'  {cam}: error = {np.around(ret[i], 3)} px')\n"
                    "    import json, datetime\n"
                    "    int_results = {'timestamp': datetime.datetime.now().isoformat(), 'cameras': []}\n"
                    "    for i, cam in enumerate(C):\n"
                    "        int_results['cameras'].append({'cam': cam, 'rms_px': round(float(ret[i]), 3)})\n"
                    "    res_path = os.path.join(calib_dir, 'Calib_results.json')\n"
                    "    existing = {}\n"
                    "    if os.path.exists(res_path):\n"
                    "        try:\n"
                    "            with open(res_path, 'r') as rf: existing = json.load(rf)\n"
                    "        except: pass\n"
                    "    existing['intrinsics'] = int_results\n"
                    "    with open(res_path, 'w') as wf: json.dump(existing, wf, indent=2)\n"
                    "except Exception as e:\n"
                    "    traceback.print_exc()\n"
                    "    sys.exit(1)\n"
                )
            cmd = [sys.executable, script_path]
        elif step_name == 'poseEstimation':
            # Custom pose estimation script: no cv2 windows, emits progress + preview frames
            proj_dir = self.pm.config.project_dir
            script_path = os.path.join(proj_dir, '_run_poseEstimation.py')
            preview_path = os.path.join(proj_dir, '_pose_preview.jpg')
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(
                    "import os, sys, logging, traceback, glob, time, json\n"
                    "import cv2, numpy as np\n"
                    "sys.stdout.reconfigure(encoding='utf-8')\n"
                    "logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)\n"
                    f"proj_dir = {repr(proj_dir)}\n"
                    f"preview_path = {repr(preview_path)}\n"
                    "os.chdir(proj_dir)\n"
                    "try:\n"
                    "    import toml\n"
                    "    from Pose2Sim.poseEstimation import (\n"
                    "        setup_model_class_mode, setup_backend_device,\n"
                    "        setup_pose_tracker, save_to_openpose\n"
                    "    )\n"
                    "    from Pose2Sim.common import (\n"
                    "        sort_people_sports2d, colors, thickness,\n"
                    "        draw_bounding_box, draw_keypts, draw_skel, bbox_xyxy_compute\n"
                    "    )\n"
                    "    from rtmlib.tools.object_detection.post_processings import nms\n"
                    "    from anytree import RenderTree\n"
                    "\n"
                    "    # Load config\n"
                    "    cfg = toml.load(os.path.join(proj_dir, 'Config.toml'))\n"
                    "    cfg['project']['project_dir'] = proj_dir\n"
                    "\n"
                    "    video_dir = os.path.join(proj_dir, 'videos')\n"
                    "    pose_dir = os.path.join(proj_dir, 'pose')\n"
                    "    os.makedirs(pose_dir, exist_ok=True)\n"
                    "\n"
                    "    pose_model_name = cfg['pose']['pose_model']\n"
                    "    mode = cfg['pose']['mode']\n"
                    "    vid_ext = cfg['pose']['vid_img_extension']\n"
                    "    output_format = cfg['pose']['output_format']\n"
                    "    save_video = 'to_video' in cfg['pose'].get('save_video', 'to_video')\n"
                    "    save_images = 'to_images' in cfg['pose'].get('save_video', '')\n"
                    "    overwrite_pose = cfg['pose'].get('overwrite_pose', False)\n"
                    "    det_frequency = cfg['pose'].get('det_frequency', 4)\n"
                    "    tracking_mode = cfg['pose'].get('tracking_mode', 'sports2d')\n"
                    "    max_distance_px = cfg['pose'].get('max_distance_px', None)\n"
                    "    frame_range = cfg['project'].get('frame_range', 'auto')\n"
                    "    backend = cfg['pose'].get('backend', 'auto')\n"
                    "    device = cfg['pose'].get('device', 'auto')\n"
                    "\n"
                    "    # Check if already done\n"
                    "    skip = False\n"
                    "    try:\n"
                    "        pose_listdirs = next(os.walk(pose_dir))[1]\n"
                    "        os.listdir(os.path.join(pose_dir, pose_listdirs[0]))[0]\n"
                    "        if not overwrite_pose:\n"
                    "            logging.info('Skipping pose estimation (already done). Set overwrite_pose=true to redo.')\n"
                    "            skip = True\n"
                    "        else:\n"
                    "            logging.info('Overwriting previous pose estimation.')\n"
                    "    except:\n"
                    "        pass\n"
                    "\n"
                    "    if not skip:\n"
                    "        # Setup model\n"
                    "        logging.info('Setting up pose model...')\n"
                    "        pose_model, ModelClass, mode = setup_model_class_mode(pose_model_name, mode, cfg)\n"
                    "        backend, device = setup_backend_device(backend=backend, device=device)\n"
                    "        pose_tracker = setup_pose_tracker(ModelClass, det_frequency, mode, False, backend, device)\n"
                    "        logging.info(f'Pose model: {pose_model_name}, mode: {mode}, backend: {backend}, device: {device}')\n"
                    "\n"
                    "        video_files = sorted(glob.glob(os.path.join(video_dir, '*' + vid_ext)))\n"
                    "        if not video_files:\n"
                    "            raise FileNotFoundError(f'No video files with {vid_ext} extension in {video_dir}')\n"
                    "\n"
                    "        keypoints_ids = [node.id for _, _, node in RenderTree(pose_model) if node.id is not None]\n"
                    "        kpt_id_max = max(keypoints_ids) + 1\n"
                    "        PREVIEW_INTERVAL = 10  # save preview every N frames\n"
                    "\n"
                    "        for vi, video_path in enumerate(video_files):\n"
                    "            vid_name = os.path.basename(video_path)\n"
                    "            video_name_wo_ext = os.path.splitext(vid_name)[0]\n"
                    "            json_output_dir = os.path.join(pose_dir, f'{video_name_wo_ext}_json')\n"
                    "            output_video_path = os.path.join(pose_dir, f'{video_name_wo_ext}_pose.mp4')\n"
                    "\n"
                    "            cap = cv2.VideoCapture(video_path)\n"
                    "            cap.read()\n"
                    "            if not cap.read()[0]:\n"
                    "                logging.warning(f'Cannot read {vid_name}, skipping.')\n"
                    "                continue\n"
                    "            cap.release()\n"
                    "            cap = cv2.VideoCapture(video_path)\n"
                    "            W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))\n"
                    "            H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))\n"
                    "            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))\n"
                    "            fps = round(cap.get(cv2.CAP_PROP_FPS))\n"
                    "\n"
                    "            f_range = [0, total_frames] if frame_range in ('all', 'auto', []) else list(frame_range)\n"
                    "            cap.set(cv2.CAP_PROP_POS_FRAMES, f_range[0])\n"
                    "            frame_idx = f_range[0]\n"
                    "\n"
                    "            # Video writer\n"
                    "            out_writer = None\n"
                    "            if save_video:\n"
                    "                fourcc = cv2.VideoWriter_fourcc(*'mp4v')\n"
                    "                out_writer = cv2.VideoWriter(output_video_path, fourcc, fps, (W, H))\n"
                    "\n"
                    "            pose_tracker.reset()\n"
                    "            prev_keypoints = None\n"
                    "            logging.info(f'\\n[POSE_START] {vid_name} ({vi+1}/{len(video_files)}) — {f_range[1]-f_range[0]} frames')\n"
                    "\n"
                    "            while cap.isOpened() and frame_idx < f_range[1]:\n"
                    "                success, frame = cap.read()\n"
                    "                if not success:\n"
                    "                    break\n"
                    "\n"
                    "                try:\n"
                    "                    keypoints, scores = pose_tracker(frame)\n"
                    "                    frame_shape = frame.shape\n"
                    "                    mask_scores = np.mean(scores, axis=1) > 0.2\n"
                    "                    likely_keypoints = np.where(mask_scores[:, np.newaxis, np.newaxis], keypoints, np.nan)\n"
                    "                    likely_scores = np.where(mask_scores[:, np.newaxis], scores, np.nan)\n"
                    "                    likely_bboxes = bbox_xyxy_compute(frame_shape, likely_keypoints, padding=0)\n"
                    "                    score_likely_bboxes = np.nanmean(likely_scores, axis=1)\n"
                    "                    valid_indices = np.where(~np.isnan(score_likely_bboxes))[0]\n"
                    "                    if len(valid_indices) > 0:\n"
                    "                        valid_bboxes = likely_bboxes[valid_indices]\n"
                    "                        valid_scores = score_likely_bboxes[valid_indices]\n"
                    "                        keep_valid = nms(valid_bboxes, valid_scores, nms_thr=0.45)\n"
                    "                        keep = valid_indices[keep_valid]\n"
                    "                    else:\n"
                    "                        keep = []\n"
                    "                    keypoints, scores = likely_keypoints[keep], likely_scores[keep]\n"
                    "\n"
                    "                    if tracking_mode == 'sports2d':\n"
                    "                        if prev_keypoints is None:\n"
                    "                            prev_keypoints = keypoints\n"
                    "                        prev_keypoints, keypoints, scores = sort_people_sports2d(prev_keypoints, keypoints, scores=scores, max_dist=max_distance_px)\n"
                    "                except:\n"
                    "                    keypoints = np.full((1, kpt_id_max, 2), fill_value=np.nan)\n"
                    "                    scores = np.full((1, kpt_id_max), fill_value=np.nan)\n"
                    "\n"
                    "                # Save JSON\n"
                    "                if 'openpose' in output_format:\n"
                    "                    json_file_path = os.path.join(json_output_dir, f'{video_name_wo_ext}_{frame_idx:06d}.json')\n"
                    "                    save_to_openpose(json_file_path, keypoints, scores)\n"
                    "\n"
                    "                # Draw skeleton for video / preview\n"
                    "                need_draw = save_video or (frame_idx % PREVIEW_INTERVAL == 0)\n"
                    "                if need_draw:\n"
                    "                    valid_X, valid_Y, valid_scores_draw = [], [], []\n"
                    "                    for pk, ps in zip(keypoints, scores):\n"
                    "                        valid_X.append(pk[:, 0])\n"
                    "                        valid_Y.append(pk[:, 1])\n"
                    "                        valid_scores_draw.append(ps)\n"
                    "                    img_show = frame.copy()\n"
                    "                    img_show = draw_bounding_box(img_show, valid_X, valid_Y, colors=colors, fontSize=2, thickness=thickness)\n"
                    "                    img_show = draw_keypts(img_show, valid_X, valid_Y, valid_scores_draw, cmap_str='RdYlGn')\n"
                    "                    img_show = draw_skel(img_show, valid_X, valid_Y, pose_model)\n"
                    "\n"
                    "                    if save_video and out_writer:\n"
                    "                        out_writer.write(img_show)\n"
                    "\n"
                    "                    # Write preview frame periodically\n"
                    "                    if frame_idx % PREVIEW_INTERVAL == 0:\n"
                    "                        scale = min(640 / W, 480 / H, 1.0)\n"
                    "                        pw, ph = int(W * scale), int(H * scale)\n"
                    "                        preview = cv2.resize(img_show, (pw, ph))\n"
                    "                        cv2.imwrite(preview_path, preview, [cv2.IMWRITE_JPEG_QUALITY, 70])\n"
                    "\n"
                    "                # Progress line\n"
                    "                rel = frame_idx - f_range[0]\n"
                    "                total = f_range[1] - f_range[0]\n"
                    "                if rel % 5 == 0 or rel == total - 1:\n"
                    "                    pct = round(100 * rel / max(total, 1))\n"
                    "                    print(f'[PROGRESS]{rel}/{total}/{vid_name}/{vi+1}/{len(video_files)}/{pct}', flush=True)\n"
                    "\n"
                    "                frame_idx += 1\n"
                    "\n"
                    "            cap.release()\n"
                    "            if out_writer:\n"
                    "                out_writer.release()\n"
                    "                logging.info(f'Output video saved: {output_video_path}')\n"
                    "            logging.info(f'Pose estimation done for {vid_name}.')\n"
                    "\n"
                    "    # Clean up preview\n"
                    "    if os.path.exists(preview_path):\n"
                    "        os.remove(preview_path)\n"
                    "    logging.info('All pose estimation complete.')\n"
                    "except Exception as e:\n"
                    "    traceback.print_exc()\n"
                    "    sys.exit(1)\n"
                )
            cmd = [sys.executable, '-u', script_path]  # -u for unbuffered output
        else:
            # Write script file for all other steps (avoids -c encoding issues with Korean paths)
            proj_dir = self.pm.config.project_dir
            script_path = os.path.join(proj_dir, f'_run_{step_name}.py')
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(
                    "import os, sys, traceback\n"
                    "sys.stdout.reconfigure(encoding='utf-8')\n"
                    f"os.chdir({repr(proj_dir)})\n"
                    "try:\n"
                    f"    from Pose2Sim import Pose2Sim; Pose2Sim.{step_name}()\n"
                    "except Exception as e:\n"
                    "    traceback.print_exc()\n"
                    "    sys.exit(1)\n"
                )
            cmd = [sys.executable, script_path]

        def worker():
            try:
                self._worker_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.pm.config.project_dir,
                )
                for line in self._worker_proc.stdout:
                    line = line.rstrip()
                    if line:
                        with self._log_lock:
                            self._log_buffer.append(line)

                self._worker_proc.wait()
                rc = self._worker_proc.returncode
                if rc == 0:
                    with self._log_lock:
                        self._log_buffer.append("[SUCCESS] Step completed successfully.")
                    self.pm.set_step_status(step_idx, StepStatus.DONE)
                else:
                    with self._log_lock:
                        self._log_buffer.append(f"[ERROR] Process exited with code {rc}")
                    self.pm.set_step_status(step_idx, StepStatus.ERROR)
            except Exception as e:
                with self._log_lock:
                    self._log_buffer.append(f"[ERROR] {str(e)}")
                self.pm.set_step_status(step_idx, StepStatus.ERROR)
            finally:
                self._running = False
                self._worker_proc = None
                # Clean up temp script
                try:
                    if os.path.exists(script_path):
                        os.remove(script_path)
                except Exception:
                    pass

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
        return {"success": True}

    def abort_step(self):
        """Abort the currently running pipeline step."""
        if self._worker_proc:
            try:
                self._worker_proc.terminate()
                with self._log_lock:
                    self._log_buffer.append("[WARNING] Step aborted by user.")
            except Exception:
                pass
        self._running = False
        return {"success": True}

    def poll_logs(self):
        """Poll new log lines since last call. Called by JS on interval."""
        with self._log_lock:
            lines = list(self._log_buffer)
            self._log_buffer.clear()
        return {"lines": lines, "running": self._running}

    def is_running(self):
        return self._running

    # ─── File System Helpers ──────────────────────────────────────

    def list_directory(self, path):
        """List files and folders in a directory."""
        try:
            if not os.path.isdir(path):
                return {"success": False, "error": "Not a directory"}
            entries = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                entries.append({
                    "name": name,
                    "path": full,
                    "is_dir": os.path.isdir(full),
                })
            return {"success": True, "entries": entries}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_camera_videos(self):
        """List video files found in videos/ - supports both flat files and subfolders."""
        proj = self.pm.config.project_dir
        if not proj:
            return []
        videos = os.path.join(proj, "videos")
        if not os.path.isdir(videos):
            return []
        result = []
        # Check for subdirectory layout (cam01/, cam02/, ...)
        cam_dirs = sorted(glob.glob(os.path.join(videos, "cam*", "")))
        if cam_dirs:
            for cam_dir in cam_dirs:
                cam_name = os.path.basename(cam_dir.rstrip(os.sep))
                files = sorted(glob.glob(os.path.join(cam_dir, "*")))
                video_files = [f for f in files if os.path.isfile(f)]
                result.append({"camera": cam_name, "files": video_files})
        else:
            # Flat layout: cam01.mp4, cam02.mp4, ... directly in videos/
            video_exts = ('.mp4', '.avi', '.mov', '.mkv')
            for f in sorted(os.listdir(videos)):
                full = os.path.join(videos, f)
                if os.path.isfile(full) and os.path.splitext(f)[1].lower() in video_exts:
                    result.append({"camera": f, "files": [full]})
        return result

    def list_trc_files(self):
        """Find .trc files in the project directory."""
        proj = self.pm.config.project_dir
        if not proj:
            return []
        trc_files = glob.glob(os.path.join(proj, "**", "*.trc"), recursive=True)
        return sorted(trc_files)

    def read_trc_info(self, trc_path):
        """Read TRC file header and return marker names, frame count, frame rate."""
        try:
            if not os.path.isfile(trc_path):
                return {"success": False, "error": "File not found"}
            with open(trc_path, 'r') as f:
                lines = []
                for i, line in enumerate(f):
                    lines.append(line.rstrip('\n'))
                    if i >= 5:
                        break
            # TRC format: line 0=header, line 1=metadata, line 2=data rate info, line 3=marker names
            if len(lines) < 4:
                return {"success": False, "error": "Invalid TRC file"}
            # Line 2: DataRate CameraRate NumFrames NumMarkers Units OrigDataRate OrigDataStartFrame OrigNumFrames
            meta_parts = lines[2].split('\t')
            frame_rate = float(meta_parts[0]) if len(meta_parts) > 0 else 0
            num_frames = int(meta_parts[2]) if len(meta_parts) > 2 else 0
            num_markers = int(meta_parts[3]) if len(meta_parts) > 3 else 0
            units = meta_parts[4] if len(meta_parts) > 4 else ''
            # Line 3: marker names (tab-separated, first two cols are Frame# and Time)
            marker_parts = lines[3].split('\t')
            markers = [m.strip() for m in marker_parts[2:] if m.strip()]
            # Remove duplicate X/Y/Z columns — every 3rd entry is a new marker
            unique_markers = []
            for i, m in enumerate(markers):
                if m and m not in unique_markers:
                    unique_markers.append(m)
            return {
                "success": True,
                "frame_rate": frame_rate,
                "num_frames": num_frames,
                "num_markers": num_markers,
                "units": units,
                "markers": unique_markers,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_calibration_files(self):
        """List calibration video/image files per camera."""
        proj = self.pm.config.project_dir
        if not proj:
            return {"intrinsics": [], "extrinsics": []}

        intrinsics = []
        int_dir = os.path.join(proj, "calibration", "intrinsics")
        if os.path.isdir(int_dir):
            for cam in sorted(os.listdir(int_dir)):
                cam_path = os.path.join(int_dir, cam)
                if os.path.isdir(cam_path):
                    files = sorted(glob.glob(os.path.join(cam_path, "*")))
                    intrinsics.append({"camera": cam, "files": files})

        extrinsics = []
        ext_dir = os.path.join(proj, "calibration", "extrinsics")
        if os.path.isdir(ext_dir):
            for cam in sorted(os.listdir(ext_dir)):
                cam_path = os.path.join(ext_dir, cam)
                if os.path.isdir(cam_path):
                    files = sorted(glob.glob(os.path.join(cam_path, "*")))
                    extrinsics.append({"camera": cam, "files": files})

        return {"intrinsics": intrinsics, "extrinsics": extrinsics}

    # ─── Step Status ──────────────────────────────────────────────

    def get_step_statuses(self):
        """Return list of step statuses [0=LOCKED, 1=READY, 2=RUNNING, 3=DONE, 4=ERROR]."""
        return self.pm.config.step_status

    def set_step_done(self, step_idx):
        """Manually mark a step as done (e.g., skip)."""
        self.pm.set_step_status(step_idx, StepStatus.DONE)
        return {"success": True}

    # ─── TRC 3D Data ─────────────────────────────────────────────

    def read_trc_data(self, trc_path, step=1):
        """
        Read full TRC data for 3D visualization.
        Returns marker names and frame data (subsampled by `step`).
        """
        try:
            if not os.path.isfile(trc_path):
                return {"success": False, "error": "File not found"}
            with open(trc_path, 'r') as f:
                raw = f.readlines()
            if len(raw) < 6:
                return {"success": False, "error": "TRC file too short"}
            # Parse header
            meta = raw[2].strip().split('\t')
            fps = float(meta[0]) if len(meta) > 0 else 30.0
            marker_line = raw[3].strip().split('\t')
            markers = []
            for m in marker_line[2:]:
                m = m.strip()
                if m and m not in markers:
                    markers.append(m)
            # Parse data rows (skip header lines 0-4)
            frames = []
            for i in range(5, len(raw), step):
                parts = raw[i].strip().split('\t')
                if len(parts) < 3:
                    continue
                frame_idx = int(float(parts[0]))
                time_val = float(parts[1])
                coords = []
                vals = parts[2:]
                for j in range(0, len(markers) * 3, 3):
                    if j + 2 < len(vals):
                        try:
                            x, y, z = float(vals[j]), float(vals[j+1]), float(vals[j+2])
                        except (ValueError, IndexError):
                            x, y, z = None, None, None
                    else:
                        x, y, z = None, None, None
                    coords.append([x, y, z])
                frames.append({"f": frame_idx, "t": time_val, "p": coords})
            return {
                "success": True,
                "fps": fps,
                "markers": markers,
                "frames": frames,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── In-Window Calibration ────────────────────────────────────

    def get_reference_image(self):
        """Load reference.png from the project calibration folder as base64."""
        try:
            proj = self.pm.config.project_dir
            if not proj:
                return {"success": False}
            ref_path = os.path.join(proj, "calibration", "reference.png")
            if not os.path.exists(ref_path):
                return {"success": False}
            with open(ref_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('ascii')
            return {"success": True, "image": data}
        except Exception:
            return {"success": False}

    def get_extrinsic_frame(self, cam_index):
        """
        Extract first frame from extrinsic calibration video/image for a camera.
        Returns base64-encoded JPEG image + image dimensions.
        """
        try:
            proj = self.pm.config.project_dir
            if not proj:
                return {"success": False, "error": "No project loaded"}
            ext_dir = os.path.join(proj, "calibration", "extrinsics")
            if not os.path.isdir(ext_dir):
                return {"success": False, "error": "No extrinsics directory"}
            cam_dirs = sorted([d for d in os.listdir(ext_dir)
                              if os.path.isdir(os.path.join(ext_dir, d))])
            if cam_index >= len(cam_dirs):
                return {"success": False, "error": f"Camera {cam_index} not found"}
            cam_dir = os.path.join(ext_dir, cam_dirs[cam_index])
            cam_name = cam_dirs[cam_index]
            # Find first video or image
            files = sorted(os.listdir(cam_dir))
            img = None
            vid_exts = ('.mp4', '.avi', '.mov', '.mkv')
            img_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')
            for f in files:
                full = os.path.join(cam_dir, f)
                ext = os.path.splitext(f)[1].lower()
                if ext in vid_exts:
                    cap = cv2.VideoCapture(full)
                    ret, img = cap.read()
                    cap.release()
                    if ret:
                        break
                elif ext in img_exts:
                    img = cv2.imread(full)
                    if img is not None:
                        break
            if img is None:
                return {"success": False, "error": "No image/video found"}
            h, w = img.shape[:2]
            # Resize for web display if too large (max 1600px wide)
            max_w = 1600
            if w > max_w:
                scale = max_w / w
                img = cv2.resize(img, (max_w, int(h * scale)))
                h, w = img.shape[:2]
            _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            b64 = base64.b64encode(buf).decode('utf-8')
            return {
                "success": True,
                "image": b64,
                "width": w,
                "height": h,
                "cam_name": cam_name,
                "cam_index": cam_index,
                "total_cameras": len(cam_dirs),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_object_coords_3d(self):
        """Read 3D object coordinates from Config.toml for calibration."""
        try:
            cfg = load_toml(self.pm.config.project_dir)
            scene = cfg.get('calibration', {}).get('calculate', {}).get('extrinsics', {}).get('scene', {})
            coords = scene.get('object_coords_3d', [])
            return {"success": True, "coords": coords}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_image_points(self):
        """
        Load previously clicked 2D points from Image_points.json.
        Returns a dict mapping cam_name → [[x,y], ...] for each camera.
        """
        try:
            proj = self.pm.config.project_dir
            if not proj:
                return {"success": False, "error": "No project loaded"}
            img_pts_path = os.path.join(proj, "calibration", "Image_points.json")
            if not os.path.exists(img_pts_path):
                return {"success": True, "cameras": {}}
            with open(img_pts_path, 'r') as f:
                data = json.load(f)
            cameras = {}
            for entry in data.get("extrinsics", []):
                cam_name = entry.get("cam_name", "")
                flat_2d = entry.get("image_points_2d", [])
                # Convert flat [x1,y1,x2,y2,...] → [[x1,y1],[x2,y2],...]
                pts = [[flat_2d[i], flat_2d[i+1]] for i in range(0, len(flat_2d), 2)]
                if cam_name and pts:
                    cameras[cam_name] = pts
            return {"success": True, "cameras": cameras}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_calibration_with_points(self, all_points_2d):
        """
        Run full calibration using manually clicked 2D points.
        all_points_2d: list of {cam_name, points: [[x,y], ...]} per camera.
        Performs intrinsic loading + extrinsic solvePnP + saves Calib_scene.toml.
        Merges with existing Calib_scene.toml so cameras not in the payload keep their extrinsics.
        """
        try:
            proj = self.pm.config.project_dir
            if not proj:
                return {"success": False, "error": "No project loaded"}
            cfg = load_toml(proj)
            calib_dir = os.path.join(proj, "calibration")

            # Load object 3D coords from config
            scene_cfg = cfg.get('calibration', {}).get('calculate', {}).get('extrinsics', {}).get('scene', {})
            object_coords_3d = np.array(scene_cfg.get('object_coords_3d', []), dtype=np.float32)
            if len(object_coords_3d) == 0:
                return {"success": False, "error": "No object_coords_3d in Config.toml"}

            # Load intrinsics from existing Calib_intrinsics_only.toml or Calib_scene.toml
            intrinsics_path = os.path.join(calib_dir, "Calib_intrinsics_only.toml")
            if not os.path.exists(intrinsics_path):
                intrinsics_path = os.path.join(calib_dir, "Calib_scene.toml")
            if not os.path.exists(intrinsics_path):
                return {"success": False, "error": "No intrinsics calibration file found. Run intrinsics first."}

            import toml
            calib_data = toml.load(intrinsics_path)

            # Build camera data from intrinsics
            cam_names = []
            cam_sizes = []
            cam_K = []
            cam_D = []
            for key, val in calib_data.items():
                if isinstance(val, dict) and 'matrix' in val:
                    cam_names.append(key)
                    cam_sizes.append(val.get('size', [1920, 1080]))
                    cam_K.append(np.array(val['matrix'], dtype=np.float64))
                    cam_D.append(np.array(val.get('distortions', [0, 0, 0, 0]), dtype=np.float64))

            if len(cam_names) == 0:
                return {"success": False, "error": "No camera data in intrinsics file"}

            # Load existing Calib_scene.toml to preserve extrinsics of cameras not being re-calibrated
            existing_scene_path = os.path.join(calib_dir, "Calib_scene.toml")
            existing_scene = {}
            if os.path.exists(existing_scene_path):
                try:
                    existing_scene = toml.load(existing_scene_path)
                except Exception:
                    pass

            # Process each camera's clicked points → per-camera R/T dict
            solved = {}  # cam_name → {r, t, rms}
            results_per_cam = []

            for cam_data in all_points_2d:
                cam_idx = cam_data.get('cam_index', 0)
                pts_2d = np.array(cam_data['points'], dtype=np.float32)

                if cam_idx >= len(cam_K):
                    results_per_cam.append({"cam": cam_data.get('cam_name', ''), "error": "No intrinsics for this camera"})
                    continue

                mtx = cam_K[cam_idx]
                dist = cam_D[cam_idx]

                if len(pts_2d) < 6:
                    results_per_cam.append({"cam": cam_names[cam_idx], "error": "Need at least 6 points"})
                    continue

                # Select corresponding object points
                objp = object_coords_3d[:len(pts_2d)]
                # solvePnP expects mm
                success, r, t = cv2.solvePnP(objp * 1000, pts_2d, mtx, dist)
                if not success:
                    results_per_cam.append({"cam": cam_names[cam_idx], "error": "solvePnP failed"})
                    continue

                r = r.flatten()
                t = t.flatten() / 1000.0  # back to meters

                # Compute reprojection error
                proj_pts, _ = cv2.projectPoints(objp * 1000, r, t * 1000, mtx, dist)
                proj_pts = proj_pts.squeeze()
                errors = np.sqrt(np.sum((proj_pts - pts_2d) ** 2, axis=1))
                rms = np.sqrt(np.mean(errors ** 2))

                solved[cam_names[cam_idx]] = {"r": r.tolist(), "t": t.tolist(), "rms": float(rms)}
                results_per_cam.append({
                    "cam": cam_names[cam_idx],
                    "rms_px": round(float(rms), 2),
                    "r": r.tolist(),
                    "t": t.tolist(),
                })

            # Save to Calib_scene.toml — merge new results with existing extrinsics
            output = {}
            for i, name in enumerate(cam_names):
                entry = {
                    "name": name,
                    "size": cam_sizes[i] if isinstance(cam_sizes[i], list) else cam_sizes[i].tolist(),
                    "matrix": cam_K[i].tolist(),
                    "distortions": cam_D[i].tolist(),
                    "fisheye": False,
                }
                if name in solved:
                    # Use newly computed extrinsics
                    entry["rotation"] = solved[name]["r"]
                    entry["translation"] = solved[name]["t"]
                elif name in existing_scene and "rotation" in existing_scene[name]:
                    # Preserve existing extrinsics for cameras not re-calibrated
                    entry["rotation"] = existing_scene[name]["rotation"]
                    entry["translation"] = existing_scene[name]["translation"]
                output[name] = entry

            out_path = os.path.join(calib_dir, "Calib_scene.toml")
            with open(out_path, 'w') as f:
                toml.dump(output, f)

            # Save Image_points.json — merge per-camera (preserve points for cameras not re-clicked)
            img_pts_path = os.path.join(calib_dir, "Image_points.json")
            img_pts_data = {}
            if os.path.exists(img_pts_path):
                try:
                    with open(img_pts_path, 'r') as f:
                        img_pts_data = json.load(f)
                except Exception:
                    pass

            # Build lookup of existing extrinsic entries by cam_name
            existing_ext = {}
            for entry in img_pts_data.get("extrinsics", []):
                existing_ext[entry.get("cam_name", "")] = entry

            # Update with newly clicked cameras
            for cam_data in all_points_2d:
                cam_name = cam_data.get('cam_name', '')
                flat_2d = []
                for pt in cam_data['points']:
                    flat_2d.extend([float(pt[0]), float(pt[1])])
                flat_3d = []
                for pt in object_coords_3d[:len(cam_data['points'])]:
                    flat_3d.extend([float(pt[0]), float(pt[1]), float(pt[2])])
                existing_ext[cam_name] = {
                    "cam_name": cam_name,
                    "image_points_2d": flat_2d,
                    "object_points_3d": flat_3d,
                }

            img_pts_data["extrinsics"] = list(existing_ext.values())
            with open(img_pts_path, 'w') as f:
                json.dump(img_pts_data, f, indent=2)

            # Save calibration results for later display (merge with intrinsics if present)
            import datetime
            results_path = os.path.join(calib_dir, "Calib_results.json")
            existing = {}
            if os.path.exists(results_path):
                try:
                    with open(results_path, 'r') as f:
                        existing = json.load(f)
                except Exception:
                    pass
            # Merge per-camera extrinsic results (preserve cameras not re-calibrated)
            prev_ext_cams = {}
            if "extrinsics" in existing and "cameras" in existing["extrinsics"]:
                for c in existing["extrinsics"]["cameras"]:
                    prev_ext_cams[c.get("cam", "")] = c
            for c in results_per_cam:
                prev_ext_cams[c.get("cam", "")] = c
            existing["extrinsics"] = {
                "timestamp": datetime.datetime.now().isoformat(),
                "cameras": list(prev_ext_cams.values()),
                "output_path": out_path,
            }
            with open(results_path, 'w') as f:
                json.dump(existing, f, indent=2)

            self.pm.set_step_status(1, StepStatus.DONE)
            return {
                "success": True,
                "output_path": out_path,
                "cameras": results_per_cam,
            }
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    # ─── Synchronization & Video Trimming ──────────────────────────

    def compute_sync_offsets(self):
        """
        Derive per-camera sync offsets by comparing frame numbering
        in pose/ vs pose-sync/ directories.
        Returns: {cameras: [{name, offset_frames, orig_frames, sync_first, sync_last}], ref_cam, fps}
        """
        try:
            proj = self.pm.config.project_dir
            if not proj:
                return {"success": False, "error": "No project loaded"}
            pose_dir = os.path.join(proj, "pose")
            sync_dir = os.path.join(proj, "pose-sync")
            if not os.path.isdir(sync_dir):
                return {"success": False, "error": "No pose-sync directory. Run synchronization first."}

            import re

            # Get FPS from Config.toml or from video
            cfg = load_toml(proj)
            fps = cfg.get('project', {}).get('frame_rate', 'auto')
            if fps == 'auto' or not isinstance(fps, (int, float)):
                # Read FPS from first video
                vid_dir = os.path.join(proj, "videos")
                vid_files = sorted(glob.glob(os.path.join(vid_dir, "*.mp4")) +
                                   glob.glob(os.path.join(vid_dir, "*.avi")) +
                                   glob.glob(os.path.join(vid_dir, "*.mov")))
                if vid_files:
                    cap = cv2.VideoCapture(vid_files[0])
                    fps = round(cap.get(cv2.CAP_PROP_FPS))
                    cap.release()
                else:
                    fps = 30

            # Get camera directories from pose-sync
            sync_cam_dirs = sorted([d for d in os.listdir(sync_dir)
                                    if os.path.isdir(os.path.join(sync_dir, d)) and d.endswith('_json')])
            if not sync_cam_dirs:
                return {"success": False, "error": "No synced pose data found in pose-sync/"}

            cameras = []
            for cam_dir_name in sync_cam_dirs:
                # Extract camera name prefix (e.g. "cam1_mo_person1" from "cam1_mo_person1_json")
                cam_prefix = cam_dir_name[:-5]  # remove "_json"

                # Get synced frame numbers
                sync_files = sorted(os.listdir(os.path.join(sync_dir, cam_dir_name)))
                sync_files = [f for f in sync_files if f.endswith('.json')]
                if not sync_files:
                    continue

                # Extract frame numbers from filenames
                def extract_frame(fname):
                    nums = re.findall(r'(\d+)', fname)
                    return int(nums[-1]) if nums else 0

                sync_frames = [extract_frame(f) for f in sync_files]
                sync_first = min(sync_frames)
                sync_last = max(sync_frames)

                # Get original frame count
                orig_dir = os.path.join(pose_dir, cam_dir_name)
                orig_count = 0
                if os.path.isdir(orig_dir):
                    orig_count = len([f for f in os.listdir(orig_dir) if f.endswith('.json')])

                cameras.append({
                    "name": cam_prefix,
                    "dir_name": cam_dir_name,
                    "sync_first": sync_first,
                    "sync_last": sync_last,
                    "sync_count": len(sync_files),
                    "orig_count": orig_count,
                })

            if not cameras:
                return {"success": False, "error": "No camera data found"}

            # Find common frame range (intersection of all cameras' synced ranges)
            common_first = max(c["sync_first"] for c in cameras)
            common_last = min(c["sync_last"] for c in cameras)

            # Reference camera = the one with the fewest original frames
            ref_idx = min(range(len(cameras)), key=lambda i: cameras[i]["orig_count"])

            return {
                "success": True,
                "cameras": cameras,
                "ref_cam": cameras[ref_idx]["name"],
                "fps": fps,
                "common_first": common_first,
                "common_last": common_last,
                "common_frames": max(0, common_last - common_first + 1),
            }
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def trim_synced_videos(self):
        """
        Trim original videos to the common synchronized frame range
        and save to videos-sync/ directory.
        Uses the sync offsets derived from pose-sync/ JSON numbering.
        """
        if self._running:
            return {"success": False, "error": "A step is already running"}

        proj = self.pm.config.project_dir
        if not proj:
            return {"success": False, "error": "No project loaded"}

        # First compute offsets
        offsets = self.compute_sync_offsets()
        if not offsets.get("success"):
            return offsets

        cameras = offsets["cameras"]
        fps = offsets["fps"]
        common_first = offsets["common_first"]
        common_last = offsets["common_last"]

        if common_last <= common_first:
            return {"success": False, "error": "No common frame range across cameras"}

        self._running = True
        with self._log_lock:
            self._log_buffer = []

        # Write a trimming script and run as subprocess
        vid_dir = os.path.join(proj, "videos")
        out_dir = os.path.join(proj, "videos-sync")
        script_path = os.path.join(proj, "_run_trim.py")

        # Map synced frame numbers back to original frame numbers:
        # orig_frame = synced_frame - sync_first
        cam_trim_info = []
        for cam in cameras:
            # Find the video file matching this camera
            cam_short = cam["name"].split("_")[0]  # e.g. "cam1" from "cam1_mo_person1"
            vid_files = sorted(glob.glob(os.path.join(vid_dir, f"{cam_short}*")))
            vid_file = vid_files[0] if vid_files else None
            if not vid_file:
                # Try matching the full prefix
                vid_files = sorted(glob.glob(os.path.join(vid_dir, f"{cam['name']}*")))
                vid_file = vid_files[0] if vid_files else None

            cam_trim_info.append({
                "name": cam["name"],
                "vid_file": vid_file,
                "sync_first": cam["sync_first"],
                "common_first": common_first,
                "common_last": common_last,
            })

        # Write trim script — use triple-quoted template to avoid escaping issues
        trim_script = f'''import os, sys, cv2, logging
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)
out_dir = {repr(out_dir)}
os.makedirs(out_dir, exist_ok=True)
cam_info = {repr(cam_trim_info)}
fps = {fps}

try:
    for ci in cam_info:
        vid_path = ci['vid_file']
        if not vid_path or not os.path.exists(vid_path):
            logging.warning(f"Video not found for {{ci['name']}}, skipping.")
            continue
        vid_name = os.path.basename(vid_path)
        out_path = os.path.join(out_dir, vid_name)

        # Map synced frame range back to original frames
        orig_start = ci['common_first'] - ci['sync_first']
        orig_end = ci['common_last'] - ci['sync_first']
        orig_start = max(0, orig_start)

        cap = cv2.VideoCapture(vid_path)
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        vid_fps = round(cap.get(cv2.CAP_PROP_FPS))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_end = min(orig_end, total - 1)
        trim_frames = orig_end - orig_start + 1

        logging.info(f"[INFO] {{vid_name}}: trimming frames {{orig_start}}-{{orig_end}} ({{trim_frames}} frames, {{trim_frames/vid_fps:.1f}}s)")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(out_path, fourcc, vid_fps, (W, H))

        cap.set(cv2.CAP_PROP_POS_FRAMES, orig_start)
        for fi in range(trim_frames):
            ret, frame = cap.read()
            if not ret:
                break
            writer.write(frame)
            if fi % 100 == 0:
                pct = round(100 * fi / max(trim_frames, 1))
                print(f"  {{vid_name}}: {{fi}}/{{trim_frames}} ({{pct}}%)", flush=True)

        cap.release()
        writer.release()
        logging.info(f"[SUCCESS] Saved: {{out_path}}")

    logging.info(f"[SUCCESS] All trimmed videos saved to {{out_dir}}")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(trim_script)

        def worker():
            try:
                cmd = [sys.executable, '-u', script_path]
                self._worker_proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=proj,
                )
                for line in self._worker_proc.stdout:
                    line = line.rstrip()
                    if line:
                        with self._log_lock:
                            self._log_buffer.append(line)
                self._worker_proc.wait()
                rc = self._worker_proc.returncode
                with self._log_lock:
                    if rc == 0:
                        self._log_buffer.append("[SUCCESS] Video trimming completed.")
                    else:
                        self._log_buffer.append(f"[ERROR] Trim process exited with code {rc}")
            except Exception as e:
                with self._log_lock:
                    self._log_buffer.append(f"[ERROR] {str(e)}")
            finally:
                self._running = False
                self._worker_proc = None
                try:
                    os.remove(script_path)
                except Exception:
                    pass

        import threading
        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
        return {"success": True}

    def get_pose_preview(self):
        """Return the latest pose estimation preview frame as base64 JPEG."""
        try:
            if not self.pm or not self.pm.config.project_dir:
                return {"success": False}
            preview_path = os.path.join(self.pm.config.project_dir, '_pose_preview.jpg')
            if not os.path.exists(preview_path):
                return {"success": False}
            # Check file age — skip if stale (> 10s old)
            import time
            if time.time() - os.path.getmtime(preview_path) > 10:
                return {"success": False}
            with open(preview_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('ascii')
            return {"success": True, "image": data}
        except Exception:
            return {"success": False}

    def get_calibration_results(self):
        """Load saved calibration results (intrinsic + extrinsic reprojection errors) if available."""
        try:
            if not self.pm or not self.pm.config.project_dir:
                return {"success": False, "error": "No project loaded"}
            calib_dir = os.path.join(self.pm.config.project_dir, "calibration")
            results_path = os.path.join(calib_dir, "Calib_results.json")
            if not os.path.exists(results_path):
                return {"success": False, "error": "No calibration results found"}
            with open(results_path, 'r') as f:
                data = json.load(f)
            return {
                "success": True,
                "intrinsics": data.get("intrinsics"),
                "extrinsics": data.get("extrinsics"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
