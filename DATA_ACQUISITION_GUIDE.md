# Data Acquisition Guide — Markerless Motion Capture

> Pose2Sim GUI / Taekwondo Motion Analysis
> Last updated: 2026-03-31

---

## Overview

This document describes the required folder structure and file naming conventions for delivering raw video data to the analysis team. Following these rules exactly ensures the processing pipeline runs without manual file rearrangement.

---

## Folder Structure

Each **trial** (one recording session of one participant) is a single project folder.
The data acquisition team must deliver the folder in this structure:

```
<project_name>/
├── calibration/
│   ├── intrinsics/
│   │   ├── int_cam01_img/
│   │   │   └── cam01_intrinsic.mp4       ← checkerboard video, camera 1
│   │   ├── int_cam02_img/
│   │   │   └── cam02_intrinsic.mp4
│   │   ├── int_cam03_img/
│   │   │   └── cam03_intrinsic.mp4
│   │   └── int_cam04_img/
│   │       └── cam04_intrinsic.mp4
│   └── extrinsics/
│       ├── ext_cam01_img/
│       │   └── cam01_extrinsic.mp4        ← scene reference video, camera 1
│       ├── ext_cam02_img/
│       │   └── cam02_extrinsic.mp4
│       ├── ext_cam03_img/
│       │   └── cam03_extrinsic.mp4
│       └── ext_cam04_img/
│           └── cam04_extrinsic.mp4
└── videos/
    ├── cam01.mp4                          ← trial video, camera 1
    ├── cam02.mp4
    ├── cam03.mp4
    └── cam04.mp4
```

> Adjust `cam01`–`cam04` based on your actual camera count (2, 3, or 4).

---

## File Naming Rules

| Item | Naming Rule | Example |
|------|-------------|---------|
| **Project folder** | Participant name or trial ID, no spaces | `eunbyul`, `trial_01` |
| **Camera ID** | `cam01`, `cam02`, ... (zero-padded, two digits) | `cam01` |
| **Trial videos** | `cam{NN}.mp4` directly inside `videos/` | `videos/cam01.mp4` |
| **Intrinsic videos** | Any name, one file per folder | `int_cam01_img/checkerboard.mp4` |
| **Extrinsic videos** | Any name, one file per folder | `ext_cam01_img/scene.mp4` |

---

## Recording Requirements

### 1. Trial Videos (`videos/`)

- **One video per camera**, all recording the same performance simultaneously.
- All cameras must be started **within ~2 seconds** of each other (the pipeline synchronizes automatically, but large offsets cannot be recovered).
- **Resolution**: 4K (3840x2160) recommended. 1080p minimum.
- **Frame rate**: All cameras must use the **same frame rate** (30 fps recommended).
- **Codec**: H.264 or H.265 in `.mp4` container.
- **Rotation**: Videos must be **landscape orientation** with correct pixel data. If your phone records in portrait, re-encode with ffmpeg to bake the rotation into the pixel data before delivery:
  ```bash
  ffmpeg -i input.mp4 -c:v libx264 -crf 18 -c:a copy output.mp4
  ```
  Alternatively, lock your phone to landscape before recording.

### 2. Intrinsic Calibration Videos (`calibration/intrinsics/`)

- Record **one video per camera** of a checkerboard pattern.
- Slowly move the checkerboard through the full field of view (center, corners, edges).
- The checkerboard must be **fully visible** (all corners) in every frame used.
- Duration: **15–30 seconds** is sufficient.
- Keep the camera **fixed on a tripod** (same position as the trial).
- Must be recorded with the **same camera settings** (resolution, focal length, zoom) as the trial videos.
- Checkerboard spec (confirm with the analysis team):
  - Inner corners: **4 columns x 5 rows**
  - Square size: **35 mm**

### 3. Extrinsic Calibration Videos (`calibration/extrinsics/`)

- Record **one video per camera** showing the scene with known reference points visible.
- The camera must be in the **exact same position and orientation** as during the trial.
- Reference points: physical markers placed on the floor/scene at **known 3D coordinates** (coordinate system decided before the session).
- The reference points must be **clearly visible and distinguishable** in the video frame.
- A single frame will be extracted — the reference points just need to be visible in the **first frame**.
- Duration: a few seconds is enough.

---

## Coordinate System for Reference Points

The 3D reference points used in extrinsic calibration are defined in **meters** with the convention:

```
      Y (up)
      │
      │
      └──── X (right)
     /
    Z (forward / toward cameras)
```

Current reference point layout (2 x 5 grid, 10 points):

| Point | X (m) | Y (m) | Z (m) |
|-------|-------|-------|-------|
| 1     | 0.0   | 0.0   | 0.0   |
| 2     | 0.0   | 0.4   | 0.0   |
| 3     | 0.0   | 0.8   | 0.0   |
| 4     | 0.0   | 1.2   | 0.0   |
| 5     | 0.0   | 1.6   | 0.0   |
| 6     | 0.8   | 0.0   | 0.0   |
| 7     | 0.8   | 0.4   | 0.0   |
| 8     | 0.8   | 0.8   | 0.0   |
| 9     | 0.8   | 1.2   | 0.0   |
| 10    | 0.8   | 1.6   | 0.0   |

> These points should be physically marked (tape, stickers) on the recording surface before the session begins. All cameras must be able to see **at least 6** of these points.

---

## Checklist Before Delivery

- [ ] All cameras use the **same frame rate** and resolution
- [ ] Videos are in **landscape orientation** (rotation metadata baked in)
- [ ] Trial videos named `cam01.mp4`, `cam02.mp4`, ... inside `videos/`
- [ ] Each camera has a corresponding intrinsic folder (`int_cam01_img/`, ...)
- [ ] Each camera has a corresponding extrinsic folder (`ext_cam01_img/`, ...)
- [ ] Checkerboard was filmed with the **same camera settings** as trial videos
- [ ] Extrinsic videos were filmed from the **exact camera positions** used in the trial
- [ ] Reference points are **clearly visible** in the extrinsic videos
- [ ] No extra files (thumbnails, `.AAE`, `.DS_Store`) inside the video folders
- [ ] Folder delivered as a single zip or directly copied to the shared drive

---

## Example: 4-Camera Setup

```
taekwondo_eunbyul/
├── calibration/
│   ├── intrinsics/
│   │   ├── int_cam01_img/
│   │   │   └── cam01_intrinsic.mp4
│   │   ├── int_cam02_img/
│   │   │   └── cam02_intrinsic.mp4
│   │   ├── int_cam03_img/
│   │   │   └── cam03_intrinsic.mp4
│   │   └── int_cam04_img/
│   │       └── cam04_intrinsic.mp4
│   └── extrinsics/
│       ├── ext_cam01_img/
│       │   └── cam01_extrinsic.mp4
│       ├── ext_cam02_img/
│       │   └── cam02_extrinsic.mp4
│       ├── ext_cam03_img/
│       │   └── cam03_extrinsic.mp4
│       └── ext_cam04_img/
│           └── cam04_extrinsic.mp4
└── videos/
    ├── cam01.mp4
    ├── cam02.mp4
    ├── cam03.mp4
    └── cam04.mp4
```

---

## Contact

For questions about coordinate systems, checkerboard specifications, or camera placement, contact the analysis team before the recording session.
