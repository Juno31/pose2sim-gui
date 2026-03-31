# Pose2Sim GUI — Markerless 3D Motion Capture

A desktop application that wraps the [Pose2Sim](https://github.com/perfanalytics/pose2sim) markerless motion capture pipeline in a visual, step-by-step interface. Built for researchers who want to process multi-camera video into 3D motion data without editing config files by hand.

---

## What This App Does

You record a person with 2-4 cameras, then this app walks you through every processing step:

```
Setup  ->  Calibration  ->  2D Pose  ->  Synchronization  ->  Triangulation  ->  Filtering  ->  Visualization
```

| Step | What happens |
|---|---|
| **Setup** | Create or open a project folder, set camera count |
| **Calibration** | Compute camera lens parameters (intrinsic) and camera positions (extrinsic) |
| **2D Pose Estimation** | Detect body keypoints in each camera's video |
| **Synchronization** | Align the timelines across cameras |
| **Triangulation** | Combine 2D detections from all cameras into 3D coordinates |
| **Filtering** | Smooth the 3D trajectories |
| **Visualization** | View the 3D skeleton, export `.trc` / `.c3d` for biomechanics software |

The final output is a `.trc` file you can open in [OpenSim](https://opensim.stanford.edu/) or [Mokka](https://biomechanical-toolkit.github.io/mokka/).

---

## Prerequisites

Before you start, make sure these are installed on your computer:

### 1. Install Anaconda (or Miniconda)

Anaconda is a tool that manages Python and its packages so they don't conflict with other software on your computer.

- **Download**: https://www.anaconda.com/download
- Run the installer. Accept all default options.
- When it finishes, you should be able to open a program called **"Terminal"** (macOS/Linux) or **"Anaconda Prompt"** (Windows).

> **How to check if Anaconda is already installed:**
> Open Terminal (or Anaconda Prompt) and type:
> ```
> conda --version
> ```
> If it prints something like `conda 24.x.x`, you're good. If it says "command not found", install Anaconda first.

### 2. Install Git

Git is a tool for downloading and updating code.

- **macOS**: Open Terminal and type `git --version`. If prompted, click "Install" to get the Xcode command line tools.
- **Windows**: Download from https://git-scm.com/download/win. Use all default options.
- **Linux**: `sudo apt install git` (Ubuntu/Debian) or `sudo dnf install git` (Fedora)

> **How to check if Git is already installed:**
> ```
> git --version
> ```
> If it prints something like `git version 2.x.x`, you're good.

---

## Installation (Step by Step)

Open **Terminal** (macOS/Linux) or **Anaconda Prompt** (Windows). Then copy-paste each command below, pressing Enter after each one.

### Step 1: Download the code

```bash
git clone https://github.com/Juno31/pose2sim-gui.git
```

This creates a folder called `pose2sim-gui` on your computer.

### Step 2: Go into the folder

```bash
cd pose2sim-gui
```

### Step 3: Create the Python environment

This installs Python and all required packages into an isolated environment called `markerless`:

```bash
conda create -n markerless python=3.10 -y
```

Wait until it finishes (about 1 minute).

### Step 4: Activate the environment

```bash
conda activate markerless
```

Your terminal prompt should now show `(markerless)` at the beginning of the line.

> **Important**: You must run `conda activate markerless` every time you open a new terminal window before running the app.

### Step 5: Install the required packages

```bash
pip install pose2sim pywebview rtmlib onnxruntime opencv-contrib-python toml
```

Wait until it finishes (may take 3-5 minutes depending on your internet speed).

### Step 6: Verify the installation

```bash
python -c "import Pose2Sim; import webview; print('OK')"
```

If it prints `OK`, the installation is complete.

---

## Running the App

Every time you want to use the app:

### 1. Open Terminal (or Anaconda Prompt)

### 2. Activate the environment

```bash
conda activate markerless
```

### 3. Go to the project folder

```bash
cd pose2sim-gui
```

> **Tip**: If you don't remember where you downloaded it, you can find it by typing:
> - macOS/Linux: `find ~ -name "pose2sim-gui" -type d 2>/dev/null`
> - Windows: `dir /s /b "%USERPROFILE%\pose2sim-gui"`

### 4. Start the app

```bash
python main_web.py
```

A window will open with the GUI. If nothing happens for a few seconds, wait — the first launch may take a moment to load.

To stop the app, close the window or press `Ctrl+C` in the terminal.

---

## GPU Acceleration (Optional — NVIDIA Only)

By default, pose estimation runs on CPU. If you have an NVIDIA GPU, you can make it 5-10x faster.

> **Skip this section** if you don't have an NVIDIA GPU, or if you're on a Mac (Macs use a different GPU system).

### Check if you have an NVIDIA GPU

```bash
nvidia-smi
```

If this prints a table with your GPU info and `CUDA Version: 12.x`, continue below. If it says "command not found", you either don't have an NVIDIA GPU or the drivers aren't installed.

### Install GPU support

```bash
conda activate markerless
pip uninstall onnxruntime -y
pip install onnxruntime-gpu
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### Verify GPU is working

```bash
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

If the output includes `CUDAExecutionProvider`, GPU acceleration is active.

---

## Preparing Your Video Data

See [DATA_ACQUISITION_GUIDE.md](DATA_ACQUISITION_GUIDE.md) for detailed recording instructions.

Each project needs this folder structure:

```
my_project/
├── calibration/
│   ├── intrinsics/
│   │   ├── int_cam01_img/
│   │   │   └── (checkerboard video from camera 1)
│   │   ├── int_cam02_img/
│   │   │   └── (checkerboard video from camera 2)
│   │   └── ...
│   └── extrinsics/
│       ├── ext_cam01_img/
│       │   └── (scene video from camera 1)
│       ├── ext_cam02_img/
│       │   └── (scene video from camera 2)
│       └── ...
└── videos/
    ├── cam01.mp4          (trial video from camera 1)
    ├── cam02.mp4          (trial video from camera 2)
    └── ...
```

**Quick checklist:**
- All cameras must use the **same frame rate** (30 fps recommended)
- All cameras must use the **same resolution**
- Videos must be in **landscape orientation** (not portrait)
- File format: `.mp4` (H.264 or H.265)

---

## Using the App

### Page 0: Setup

1. Click **"New Project"** to create a new project, or **"Open Project"** to load an existing one.
2. For a new project: enter a name, choose a folder, select camera count (2-4), and pick pose estimator.
3. The app creates the required folder structure for you.

### Page 1: Calibration

**Intrinsic calibration** (camera lens parameters):
1. Place a checkerboard pattern in front of each camera and record a short video (15-30 seconds).
2. Put each video in the corresponding `int_camXX_img/` folder.
3. Set the checkerboard size (columns, rows, square size in mm).
4. Click **"Run Intrinsics Only"** and wait for it to finish.

**Extrinsic calibration** (camera positions):
1. Place reference markers at known 3D positions in your scene.
2. Record a short video from each camera showing the markers.
3. Put each video in the corresponding `ext_camXX_img/` folder.
4. Click **"Click Extrinsic Points"** — you'll see each camera's view.
5. Click on each reference point in order (zoom with scroll, pan with Alt+drag).
6. After all cameras, click **"Compute Calibration"**.
7. Check the reprojection error — below 2 px is good.

### Page 2: Processing

Each sub-step has its own **Save** and **Run** buttons:

1. **2D Pose Estimation**: Detects body keypoints in each video. A live preview shows the skeleton overlay. Takes 1-10 minutes depending on video length and GPU.
2. **Synchronization**: Aligns camera timelines. Usually takes a few seconds.
3. **Triangulation**: Combines 2D poses into 3D. Check that reprojection errors are reasonable.
4. **Filtering**: Smooths the trajectories. Default Butterworth filter works well for most cases.

### Page 3: Visualization

- Select a `.trc` file to view the 3D skeleton animation.
- Use the playback controls to scrub through frames.
- Orbit, zoom, and pan the 3D view with your mouse.

---

## Troubleshooting

### "No module named 'Pose2Sim'"
You forgot to activate the environment. Run `conda activate markerless` first.

### "No persons have been triangulated"
- Make sure you completed **both** intrinsic and extrinsic calibration.
- Check that the person is visible in at least 2 cameras throughout the recording.
- Try increasing `reproj_error_threshold_triangulation` (e.g., from 15 to 30).

### "Not a homogeneous array" during calibration
Your `Config.toml` has mixed integer/float types. Make sure all numbers in coordinate arrays are floats (use `0.0` instead of `0`).

### The app window doesn't open
- Make sure you're running `python main_web.py` (not `main.py`).
- Try: `pip install pywebview[qt]` if the default backend doesn't work.

### Pose estimation is very slow
- Check GPU setup (see GPU section above).
- Reduce video resolution to 1080p.
- Increase `det_frequency` (e.g., from 1 to 4) to run detection less often.

### Videos are rotated sideways
Phone videos recorded in portrait mode need to be re-encoded:
```bash
ffmpeg -i input.mp4 -c:v libx264 -crf 18 -c:a copy output.mp4
```

---

## Updating the App

```bash
cd pose2sim-gui
git pull
pip install --upgrade pose2sim pywebview rtmlib
```

---

## Removing Everything

```bash
conda deactivate
conda env remove -n markerless
```

Then delete the `pose2sim-gui` folder.

---

## Project Structure

```
pose2sim-gui/
├── main_web.py              # Entry point — run this to start the app
├── app/
│   ├── api.py               # Backend API (Python ↔ GUI communication)
│   ├── project.py           # Project configuration and state management
│   └── toml_bridge.py       # Config.toml read/write helpers
├── web/
│   ├── index.html           # GUI layout
│   ├── style.css            # Visual styling
│   └── app.js               # GUI logic (navigation, forms, 3D viewer)
├── environment.yml          # Conda environment definition
├── requirements.txt         # pip dependencies
├── DATA_ACQUISITION_GUIDE.md  # Recording instructions for the data team
└── README.md                # This file
```

---

## Credits

- [Pose2Sim](https://github.com/perfanalytics/pose2sim) by David Pagnon — the core markerless pipeline
- [RTMLib](https://github.com/Tau-J/rtmlib) — real-time pose estimation models
- [Three.js](https://threejs.org/) — 3D visualization in the browser
- [PyWebView](https://pywebview.flowrl.com/) — native desktop window for web UIs

## License

MIT License — see [LICENSE](LICENSE) for details.
