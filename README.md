# 🏃 Markerless

> A **PyQt5 desktop application** that wraps the [Pose2Sim](https://github.com/perfanalytics/pose2sim) 3D markerless motion capture pipeline in an intuitive, step-by-step GUI.

No more editing TOML configs by hand — just point, click, and run.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Dark scientific UI** | GitHub-dark themed, optimized for long research sessions |
| **Step-locked navigation** | Each step unlocks only after the previous one completes |
| **2 – 4 camera support** | Set camera count once; applies automatically to every step |
| **RTMLib & OpenPose** | Switch pose estimators from the setup screen |
| **Background execution** | Pipeline runs in QThread — UI stays responsive |
| **Live console output** | Color-coded log with INFO / WARNING / ERROR / SUCCESS levels |
| **Project save / load** | State persisted as `markerless_config.json` |

---

## 📋 Pipeline Steps

```
Setup → Calibration → 2D Pose → Synchronization → Triangulation → Filtering → Visualization
```

| Step | What it does |
|---|---|
| **Setup** | Create/open project, choose camera count & pose estimator |
| **Calibration** | Intrinsic (checkerboard / charuco) + Extrinsic (scene / board) |
| **2D Pose Estimation** | Detect body keypoints in each camera view |
| **Synchronization** | Align camera timelines via keypoint motion signals |
| **Triangulation** | Reconstruct 3D positions with DLT from multi-view 2D detections |
| **Filtering** | Smooth trajectories (Butterworth / Kalman / Gaussian / LOESS / Median) |
| **Visualization** | Render 3D skeleton, export `.c3d` / `.trc` for OpenSim / Mokka |

---

## ⚡ Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/markerless.git
cd markerless
```

### 2. Create the conda environment

Open **Anaconda Prompt** (Windows) or a terminal (macOS/Linux):

```bash
conda env create -f environment.yml
conda activate markerless
```

> First-time setup takes a few minutes while conda and pip download packages.

### 3. Run

```bash
python main.py
```

---

## 🎮 GPU Setup (NVIDIA only)

CPU-only works out of the box. For significantly faster pose estimation, follow these steps.

### Step 1 — Check your CUDA version

```bash
nvidia-smi
```

Look for `CUDA Version: XX.X` in the top-right corner of the output.
You need **CUDA 12.x** for the commands below.

### Step 2 — Install PyTorch with CUDA

```bash
conda activate markerless

pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

> If your `nvidia-smi` shows a different CUDA version, find the right command at
> https://pytorch.org/get-started/locally

### Step 3 — Switch to onnxruntime-gpu

```bash
pip uninstall onnxruntime -y
pip install onnxruntime-gpu
```

### Step 4 — Verify the GPU environment

Run each check in order:

**4a. Driver and CUDA**
```bash
nvidia-smi
# Top-right corner must show CUDA 12.x
```

**4b. cuDNN (via PyTorch)**
```bash
python -c "import torch; print('cuDNN version :', torch.backends.cudnn.version()); print('cuDNN available:', torch.backends.cudnn.is_available())"
# Expected: cuDNN available: True
```

**4c. ONNX Runtime providers**
```bash
python -c "import onnxruntime as ort; print('ORT version:', ort.__version__); print('Providers:', ort.get_available_providers())"
# Expected: [..., 'CUDAExecutionProvider', 'CPUExecutionProvider']
```

**4d. Full end-to-end GPU test**
```bash
python -c "
import onnxruntime as ort, onnx, numpy as np, tempfile, os
from onnx import helper, TensorProto

node  = helper.make_node('Identity', ['x'], ['y'])
graph = helper.make_graph([node], 'test',
    [helper.make_tensor_value_info('x', TensorProto.FLOAT, [1])],
    [helper.make_tensor_value_info('y', TensorProto.FLOAT, [1])])
model = helper.make_model(graph)
tmp = tempfile.mktemp(suffix='.onnx')
onnx.save(model, tmp)

sess = ort.InferenceSession(tmp, providers=['CUDAExecutionProvider'])
print('Active provider:', sess.get_providers()[0])
os.remove(tmp)
"
# Expected: Active provider: CUDAExecutionProvider
```

If the last check prints `CUDAExecutionProvider` — GPU is fully working. ✓

---

## 🔄 Updating

```bash
cd markerless
git pull
conda env update -f environment.yml --prune
```

---

## 🗑️ Removing the environment

```bash
conda deactivate
conda env remove -n markerless
```

---

## 🗂️ Project Structure

```
markerless/
│
├── main.py                        # Entry point
├── environment.yml                # Conda environment definition
├── requirements.txt               # pip dependencies (reference)
├── .gitignore
├── README.md
│
├── app/
│   ├── project.py                 # ProjectConfig dataclass + ProjectManager
│   ├── runner.py                  # QThread workers for background execution
│   └── pose2sim_api.py            # Lazy pose2sim import with clear error messages
│
├── ui/
│   ├── main_window.py             # Main window + sidebar navigation
│   ├── assets/
│   │   └── style.qss              # Global dark theme stylesheet
│   ├── components/
│   │   └── widgets.py             # PathPicker, LogWidget, StepRunWidget
│   └── tabs/
│       ├── tab_setup.py           # Project creation & loading
│       ├── tab_calibration.py     # Camera calibration
│       ├── tab_pose2d.py          # 2D pose estimation
│       ├── tab_sync.py            # Synchronization
│       ├── tab_triangulation.py   # 3D triangulation
│       ├── tab_filtering.py       # Trajectory filtering
│       └── tab_visualization.py   # 3D marker visualization
│
└── docs/
    └── GITHUB_UPLOAD.md           # Step-by-step GitHub upload guide
```

---

## 🔧 Requirements

| Requirement | Version |
|---|---|
| Python | 3.12 |
| PyQt5 | ≥ 5.15 |
| pose2sim | latest |
| CUDA *(optional)* | 12.x |
| cuDNN *(optional)* | 9.x |

Tested on **Windows 10/11**, **Ubuntu 22.04**, **macOS 13+**.

---

## 🗺️ Roadmap

- [ ] Config.toml auto-generation from GUI settings
- [ ] Camera video preview panel (OpenCV)
- [ ] "Run All" sequential pipeline mode
- [ ] Output file browser panel
- [ ] Multi-language support (EN / KO / FR)

---

## 🤝 Contributing

Pull requests are welcome!

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Credits

- [Pose2Sim](https://github.com/perfanalytics/pose2sim) by **David Pagnon** — the underlying pipeline this GUI wraps
- [RTMLib](https://github.com/Tau-J/rtmlib) — fast real-time pose estimation
- [OpenPose](https://github.com/CMU-Perceptual-Computing-Lab/openpose) — Carnegie Mellon University
