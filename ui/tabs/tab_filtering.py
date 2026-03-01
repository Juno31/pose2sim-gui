"""
ui/tabs/tab_filtering.py - Filtering Tab
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QCheckBox, QSplitter, QComboBox, QPushButton,
    QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from ui.components.widgets import StepRunWidget
from app.project import ProjectManager, StepStatus
import sys
from app.runner import ScriptWorker


class FilteringTab(QWidget):
    def __init__(self, pm: ProjectManager, parent=None):
        super().__init__(parent)
        self.pm = pm
        self.worker = None
        self._build_ui()
        pm.register_change_callback(self._on_project_changed)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Filtering")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        desc = QLabel("Smooth 3D trajectories to remove noise and artifacts from triangulation.")
        desc.setObjectName("sectionDesc")
        outer.addWidget(desc)

        # Save Config row
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("💾  Save Config")
        self.save_btn.setToolTip("Write current settings to Config.toml")
        self.save_btn.clicked.connect(self._save_config)
        save_row.addWidget(self.save_btn)
        self.save_status = QLabel("")
        self.save_status.setStyleSheet("color: #7ee787; font-size: 11px;")
        save_row.addWidget(self.save_status)
        save_row.addStretch()
        outer.addLayout(save_row)

        splitter = QSplitter(Qt.Vertical)

        group = QGroupBox("Filter Settings")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.filter_enabled = QCheckBox("Enable filtering after outlier rejection")
        self.filter_enabled.setChecked(True)
        form.addRow(self.filter_enabled)

        self.filter_type = QComboBox()
        self.filter_type.addItems(["butterworth", "kalman", "gcv_spline", "gaussian", "LOESS", "median", "butterworth_on_speed"])
        self.filter_type.currentTextChanged.connect(self._on_filter_changed)
        form.addRow("Filter Type:", self.filter_type)

        self.filter_info = QLabel()
        self.filter_info.setStyleSheet("color: #8b949e; font-size: 11px;")
        self.filter_info.setWordWrap(True)
        form.addRow(self.filter_info)

        self.cutoff_freq = QDoubleSpinBox()
        self.cutoff_freq.setRange(0.5, 50.0)
        self.cutoff_freq.setValue(6.0)
        self.cutoff_freq.setSuffix(" Hz")
        form.addRow("Cutoff Frequency:", self.cutoff_freq)

        self.filter_order = QSpinBox()
        self.filter_order.setRange(1, 10)
        self.filter_order.setValue(4)
        form.addRow("Filter Order:", self.filter_order)

        self.reject_outliers = QCheckBox("Reject outliers (Hampel filter)")
        self.reject_outliers.setChecked(True)
        form.addRow(self.reject_outliers)

        self.display = QCheckBox("Display filter results")
        form.addRow(self.display)

        self.make_c3d = QCheckBox("Also save as .c3d")
        self.make_c3d.setChecked(True)
        form.addRow(self.make_c3d)

        self.save_filt_plots = QCheckBox("Save filter plots to file")
        self.save_filt_plots.setChecked(True)
        form.addRow(self.save_filt_plots)

        # ── Type-specific sub-parameters ──────────────────────────────────────
        # Kalman
        self._kalman_trust_lbl = QLabel("Trust Ratio:")
        self.kalman_trust_ratio = QSpinBox()
        self.kalman_trust_ratio.setRange(1, 5000)
        self.kalman_trust_ratio.setValue(500)
        self.kalman_trust_ratio.setToolTip("measurement_trust / process_trust — higher = trust data more")
        form.addRow(self._kalman_trust_lbl, self.kalman_trust_ratio)

        self._kalman_smooth_lbl = QLabel("")
        self.kalman_smooth = QCheckBox("Smooth (recommended for offline)")
        form.addRow(self._kalman_smooth_lbl, self.kalman_smooth)
        self.kalman_smooth.setChecked(True)

        # GCV Spline
        self._gcv_cutoff_lbl = QLabel("Cut-off Frequency:")
        self.gcv_cutoff = QLineEdit("auto")
        self.gcv_cutoff.setToolTip("'auto' or Hz — 'auto' finds optimal per-keypoint")
        form.addRow(self._gcv_cutoff_lbl, self.gcv_cutoff)

        self._gcv_smooth_lbl = QLabel("Smoothing Factor:")
        self.gcv_smooth_factor = QDoubleSpinBox()
        self.gcv_smooth_factor.setRange(0.0, 10.0)
        self.gcv_smooth_factor.setSingleStep(0.1)
        self.gcv_smooth_factor.setValue(1.0)
        form.addRow(self._gcv_smooth_lbl, self.gcv_smooth_factor)

        # Gaussian
        self._sigma_lbl = QLabel("Sigma Kernel:")
        self.sigma_kernel = QSpinBox()
        self.sigma_kernel.setRange(1, 100)
        self.sigma_kernel.setValue(1)
        form.addRow(self._sigma_lbl, self.sigma_kernel)

        # LOESS
        self._loess_lbl = QLabel("Nb Values Used:")
        self.loess_nb = QSpinBox()
        self.loess_nb.setRange(3, 200)
        self.loess_nb.setValue(5)
        form.addRow(self._loess_lbl, self.loess_nb)

        # Median
        self._median_lbl = QLabel("Kernel Size:")
        self.median_kernel = QSpinBox()
        self.median_kernel.setRange(3, 51)
        self.median_kernel.setSingleStep(2)
        self.median_kernel.setValue(3)
        form.addRow(self._median_lbl, self.median_kernel)

        self._on_filter_changed("butterworth")
        splitter.addWidget(group)

        self.run_widget = StepRunWidget("Run Filtering")
        self.run_widget.run_requested.connect(self._run)
        self.run_widget.abort_requested.connect(self._abort)
        splitter.addWidget(self.run_widget)
        splitter.setSizes([300, 300])

        outer.addWidget(splitter)

    def _on_filter_changed(self, filter_type):
        descriptions = {
            "butterworth":          "Classic low-pass filter. Best for smooth continuous motion.",
            "kalman":               "Optimal for noisy data with known dynamics. Good for sports.",
            "gcv_spline":           "Auto-optimal spline. Best when keypoints have varying speeds.",
            "gaussian":             "Gaussian kernel smoothing. Simple and fast.",
            "LOESS":                "Local regression. Very smooth but computationally heavy.",
            "median":               "Removes spike outliers. Good for removing sudden jumps.",
            "butterworth_on_speed": "Butterworth applied to the speed signal instead of position.",
        }
        self.filter_info.setText(descriptions.get(filter_type, ""))
        needs_cutoff = filter_type in ("butterworth", "kalman", "butterworth_on_speed")
        needs_order  = filter_type in ("butterworth", "kalman", "butterworth_on_speed")
        self.cutoff_freq.setEnabled(needs_cutoff)
        self.filter_order.setEnabled(needs_order)

        # Show/hide type-specific rows
        show_kalman  = filter_type == "kalman"
        show_gcv     = filter_type == "gcv_spline"
        show_gaussian= filter_type == "gaussian"
        show_loess   = filter_type == "LOESS"
        show_median  = filter_type == "median"

        for lbl, wgt in [
            (self._kalman_trust_lbl, self.kalman_trust_ratio),
            (self._kalman_smooth_lbl, self.kalman_smooth),
        ]:
            lbl.setVisible(show_kalman)
            wgt.setVisible(show_kalman)

        for lbl, wgt in [
            (self._gcv_cutoff_lbl, self.gcv_cutoff),
            (self._gcv_smooth_lbl, self.gcv_smooth_factor),
        ]:
            lbl.setVisible(show_gcv)
            wgt.setVisible(show_gcv)

        self._sigma_lbl.setVisible(show_gaussian)
        self.sigma_kernel.setVisible(show_gaussian)
        self._loess_lbl.setVisible(show_loess)
        self.loess_nb.setVisible(show_loess)
        self._median_lbl.setVisible(show_median)
        self.median_kernel.setVisible(show_median)

    def load_from_toml(self, data: dict):
        """Populate widgets from a parsed Config.toml dict."""
        filt = data.get("filtering", {})

        val = filt.get("filter")
        if isinstance(val, bool):
            self.filter_enabled.setChecked(val)

        val = filt.get("type")
        if isinstance(val, str):
            idx = self.filter_type.findText(val)
            if idx >= 0:
                self.filter_type.setCurrentIndex(idx)

        val = filt.get("reject_outliers")
        if isinstance(val, bool):
            self.reject_outliers.setChecked(val)

        val = filt.get("display_figures")
        if isinstance(val, bool):
            self.display.setChecked(val)

        val = filt.get("make_c3d")
        if isinstance(val, bool):
            self.make_c3d.setChecked(val)

        val = filt.get("save_filt_plots")
        if isinstance(val, bool):
            self.save_filt_plots.setChecked(val)

        # Butterworth / butterworth_on_speed
        bw = filt.get("butterworth", {})
        val = bw.get("cut_off_frequency")
        if isinstance(val, (int, float)):
            self.cutoff_freq.setValue(float(val))
        val = bw.get("order")
        if isinstance(val, int):
            self.filter_order.setValue(val)

        # Kalman
        kalman = filt.get("kalman", {})
        val = kalman.get("trust_ratio")
        if isinstance(val, int):
            self.kalman_trust_ratio.setValue(val)
        val = kalman.get("smooth")
        if isinstance(val, bool):
            self.kalman_smooth.setChecked(val)

        # GCV Spline
        gcv = filt.get("gcv_spline", {})
        val = gcv.get("cut_off_frequency")
        if val is not None:
            self.gcv_cutoff.setText(str(val))
        val = gcv.get("smoothing_factor")
        if isinstance(val, (int, float)):
            self.gcv_smooth_factor.setValue(float(val))

        # Gaussian
        gaussian = filt.get("gaussian", {})
        val = gaussian.get("sigma_kernel")
        if isinstance(val, int):
            self.sigma_kernel.setValue(val)

        # LOESS
        loess = filt.get("loess", {})
        val = loess.get("nb_values_used")
        if isinstance(val, int):
            self.loess_nb.setValue(val)

        # Median
        median = filt.get("median", {})
        val = median.get("kernel_size")
        if isinstance(val, int):
            self.median_kernel.setValue(val)

    def _save_config(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.save_status.setText("✗ No project loaded")
            self.save_status.setStyleSheet("color: #f85149; font-size: 11px;")
            return
        from app.toml_bridge import save_toml_values
        gcv_cutoff_text = self.gcv_cutoff.text().strip()
        try:
            gcv_cutoff_val = int(gcv_cutoff_text) if gcv_cutoff_text != "auto" else "auto"
        except ValueError:
            gcv_cutoff_val = gcv_cutoff_text
        save_toml_values(cfg.project_dir, [
            ("filtering",             "filter",            self.filter_enabled.isChecked()),
            ("filtering",             "type",              self.filter_type.currentText()),
            ("filtering",             "reject_outliers",   self.reject_outliers.isChecked()),
            ("filtering",             "display_figures",   self.display.isChecked()),
            ("filtering",             "make_c3d",          self.make_c3d.isChecked()),
            ("filtering",             "save_filt_plots",   self.save_filt_plots.isChecked()),
            ("filtering.butterworth", "cut_off_frequency", self.cutoff_freq.value()),
            ("filtering.butterworth", "order",             self.filter_order.value()),
            ("filtering.kalman",      "trust_ratio",       self.kalman_trust_ratio.value()),
            ("filtering.kalman",      "smooth",            self.kalman_smooth.isChecked()),
            ("filtering.gcv_spline",  "cut_off_frequency", gcv_cutoff_val),
            ("filtering.gcv_spline",  "smoothing_factor",  self.gcv_smooth_factor.value()),
            ("filtering.gaussian",    "sigma_kernel",      self.sigma_kernel.value()),
            ("filtering.loess",       "nb_values_used",    self.loess_nb.value()),
            ("filtering.median",      "kernel_size",       self.median_kernel.value()),
        ])
        self.save_status.setText("✓ Config saved")
        self.save_status.setStyleSheet("color: #7ee787; font-size: 11px;")
        QTimer.singleShot(3000, lambda: self.save_status.setText(""))

    def _on_project_changed(self, cfg):
        if cfg.project_dir:
            from app.toml_bridge import load_toml
            data = load_toml(cfg.project_dir)
            if data:
                self.load_from_toml(data)

    def _run(self):
        cfg = self.pm.config
        if not cfg.project_dir:
            self.run_widget.log.append("[ERROR] No project loaded.")
            return

        cfg.filter_type    = self.filter_type.currentText()
        cfg.filter_cutoff  = self.cutoff_freq.value()
        cfg.filter_order   = self.filter_order.value()
        cfg.filter_display = self.display.isChecked()

        self.run_widget.set_running(True)
        self.run_widget.log.append(
            f"[INFO] Filter: {cfg.filter_type} | "
            f"Cutoff: {cfg.filter_cutoff}Hz | Order: {cfg.filter_order}"
        )

        cmd = [sys.executable, '-c',
               f'import os; os.chdir({repr(cfg.project_dir)}); '
               f'from Pose2Sim import Pose2Sim; Pose2Sim.filtering()']
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
            self.pm.set_step_status(5, StepStatus.DONE)
