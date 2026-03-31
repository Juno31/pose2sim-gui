/**
 * app.js - Markerless Web UI (4-page layout)
 * Pages: 0=Setup, 1=Calibration, 2=Processing, 3=Visualization
 * Modules: App (core), Calib (in-window extrinsic calibration), Viewer3D (TRC 3D viewer)
 */

// ═══════════════════════════════════════════════════════════════
// APP — Core navigation, config, pipeline
// ═══════════════════════════════════════════════════════════════

const App = {
  currentTab: 0,
  currentStepName: null,
  pollTimer: null,

  STEP_IDX: {
    calibration: 1,
    poseEstimation: 2,
    synchronization: 3,
    triangulation: 4,
    filtering: 5,
    markerAugmentation: 6,
  },

  // ─── Init ───────────────────────────────────────────────────

  async init() {
    while (!window.pywebview || !window.pywebview.api) {
      await new Promise(r => setTimeout(r, 50));
    }
    this.bindSidebar();
    this.switchTab(0);
    const cfg = await pywebview.api.get_project_config();
    if (cfg.project_dir) this.onProjectLoaded(cfg);
  },

  // ─── Sidebar ────────────────────────────────────────────────

  bindSidebar() {
    document.querySelectorAll('.nav-item').forEach(btn => {
      btn.addEventListener('click', () => this.switchTab(parseInt(btn.dataset.step)));
    });
  },

  switchTab(idx) {
    this.currentTab = idx;
    document.querySelectorAll('.tab').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    const panel = document.getElementById(`tab-${idx}`);
    const btn = document.querySelector(`.nav-item[data-step="${idx}"]`);
    if (panel) panel.classList.add('active');
    if (btn) btn.classList.add('active');
    // Resize 3D viewer when switching to visualization
    if (idx === 3 && Viewer3D._renderer) Viewer3D.resize();
  },

  async updateStepStatuses() {
    const s = await pywebview.api.get_step_statuses();
    const icons = { 0: '', 1: '', 2: '\u25CF', 3: '\u2713', 4: '\u2717' };
    this._setBadge('status-0', s[0], icons);
    this._setNavEnabled(0, true);
    this._setBadge('status-1', s[1], icons);
    this._setNavEnabled(1, s[1] !== 0);
    const procStatuses = [s[2], s[3], s[4], s[5]];
    const procAgg = this._aggregateStatus(procStatuses);
    this._setBadge('status-2', procAgg, icons);
    this._setNavEnabled(2, procStatuses.some(x => x !== 0));
    this._setSubBadge('sub-status-pose', s[2]);
    this._setSubBadge('sub-status-sync', s[3]);
    this._setSubBadge('sub-status-triang', s[4]);
    this._setSubBadge('sub-status-filt', s[5]);
    this._setBadge('status-3', s[6], icons);
    this._setNavEnabled(3, s[6] !== 0);
  },

  _aggregateStatus(statuses) {
    if (statuses.includes(4)) return 4;
    if (statuses.includes(2)) return 2;
    if (statuses.every(s => s === 0)) return 0;
    if (statuses.every(s => s === 3)) return 3;
    return 1;
  },

  _setBadge(id, status, icons) {
    const el = document.getElementById(id);
    if (el) el.textContent = icons[status] || '';
  },

  _setNavEnabled(pageIdx, enabled) {
    const btn = document.querySelector(`.nav-item[data-step="${pageIdx}"]`);
    if (btn) btn.disabled = !enabled;
  },

  _setSubBadge(id, status) {
    const el = document.getElementById(id);
    if (!el) return;
    const labels = { 0: '', 1: 'Ready', 2: 'Running', 3: 'Done', 4: 'Error' };
    const classes = { 2: 'running', 3: 'done', 4: 'error' };
    el.textContent = labels[status] || '';
    el.className = 'step-summary-badge ' + (classes[status] || '');
  },

  // ─── Project ────────────────────────────────────────────────

  async browseNewProjectDir() {
    const dir = await pywebview.api.browse_directory();
    if (dir) document.getElementById('new-project-dir').value = dir;
  },

  async browseOpenProject() {
    const dir = await pywebview.api.browse_directory();
    if (dir) document.getElementById('open-project-dir').value = dir;
  },

  async createProject() {
    const name = document.getElementById('new-project-name').value.trim();
    const dir = document.getElementById('new-project-dir').value.trim();
    const camCount = parseInt(document.querySelector('input[name="cam-count"]:checked').value);
    const estimator = document.querySelector('input[name="estimator"]:checked').value;
    if (!name) return alert('Please enter a project name.');
    if (!dir) return alert('Please select a project directory.');
    const result = await pywebview.api.new_project(name, dir, camCount, estimator);
    if (result.success) {
      this.onProjectLoaded(await pywebview.api.get_project_config());
    } else {
      alert('Error: ' + result.error);
    }
  },

  async openProject() {
    const dir = document.getElementById('open-project-dir').value.trim();
    if (!dir) return alert('Please select a project folder.');
    const result = await pywebview.api.open_project(dir);
    if (result.success) this.onProjectLoaded(result.config);
    else alert('Error: ' + result.error);
  },

  async onProjectLoaded(cfg) {
    document.getElementById('project-info').innerHTML =
      `<strong>${cfg.project_name}</strong><br>${cfg.camera_count} cameras &bull; ${cfg.pose_estimator}`;
    document.getElementById('project-params-card').style.display = '';
    await this.loadAllConfigs();
    await this.updateStepStatuses();
    await this.loadCameraVideos();
    await Calib.loadResults();
  },

  // ─── Load Config ────────────────────────────────────────────

  async loadAllConfigs() {
    const t = await pywebview.api.load_config();
    if (!t || !Object.keys(t).length) return;

    const p = t.project || {};
    this.setCheckbox('cfg-multi-person', p.multi_person);
    this.setVal('cfg-frame-rate', p.frame_rate ?? 'auto');
    this.setVal('cfg-frame-range', Array.isArray(p.frame_range) ? JSON.stringify(p.frame_range) : (p.frame_range ?? 'auto'));
    this.setVal('cfg-height', p.participant_height ?? 'auto');
    this.setVal('cfg-mass', p.participant_mass ?? 70.0);

    const ci = t.calibration?.calculate?.intrinsics || {};
    const cn = ci.intrinsics_corners_nb || [6, 9];
    this.setVal('cal-int-cols', cn[0]); this.setVal('cal-int-rows', cn[1]);
    this.setVal('cal-int-square', ci.intrinsics_square_size ?? 40.0);
    this.setVal('cal-int-extract', ci.extract_every_N_sec ?? 1.0);
    this.setSelect('cal-int-ext', ci.intrinsics_extension ?? 'jpg');
    this.setCheckbox('cal-int-overwrite', ci.overwrite_intrinsics);
    this.setCheckbox('cal-int-show', ci.show_detection_intrinsics ?? true);

    const ce = t.calibration?.calculate?.extrinsics || {};
    this.setSelect('cal-ext-method', ce.extrinsics_method ?? 'scene');
    this.setSelect('cal-ext-ext', ce.extrinsics_extension ?? 'png');
    this.setCheckbox('cal-ext-reproj', ce.show_reprojection_error ?? true);
    this.setCheckbox('cal-debug-images', (t.calibration?.calculate || {}).save_debug_images ?? true);

    const ps = t.pose || {};
    this.setSelect('pose-model', ps.pose_model ?? 'Body_with_feet');
    if (typeof ps.mode === 'string' && !ps.mode.startsWith('{')) this.setSelect('pose-mode', ps.mode);
    this.setSelect('pose-backend', ps.backend ?? 'auto');
    this.setSelect('pose-device', ps.device ?? 'auto');
    this.setVal('pose-det-freq', ps.det_frequency ?? 4);
    this.setSelect('pose-tracking', ps.tracking_mode ?? 'sports2d');
    this.setSelect('pose-vid-ext', ps.vid_img_extension ?? 'mp4');
    this.setCheckbox('pose-overwrite', ps.overwrite_pose);
    this.setCheckbox('pose-display', ps.display_detection ?? true);

    const sy = t.synchronization || {};
    this.setVal('sync-peak-time', sy.approx_time_maxspeed ?? 0.5);
    this.setVal('sync-range', sy.time_range_around_maxspeed ?? 2.0);
    this.setVal('sync-cutoff', sy.filter_cutoff ?? 6.0);
    this.setVal('sync-order', sy.filter_order ?? 4);
    this.setVal('sync-likelihood', sy.likelihood_threshold ?? 0.4);
    this.setCheckbox('sync-display', sy.display_sync_plots ?? true);
    this.setCheckbox('sync-save', sy.save_sync_plots ?? true);
    this.setCheckbox('sync-gui', sy.synchronization_gui ?? true);
    this.setVal('sync-keypoints', Array.isArray(sy.keypoints_to_consider) ? JSON.stringify(sy.keypoints_to_consider) : (sy.keypoints_to_consider ?? 'all'));

    const tr = t.triangulation || {};
    this.setVal('tri-reproj', tr.reproj_error_threshold_triangulation ?? 15.0);
    this.setVal('tri-likelihood', tr.likelihood_threshold_triangulation ?? 0.3);
    this.setVal('tri-min-cams', tr.min_cameras_for_triangulation ?? 2);
    this.setSelect('tri-interp', tr.interpolation ?? 'linear');
    this.setVal('tri-max-gap', tr.interp_if_gap_smaller_than ?? 20);
    this.setCheckbox('tri-c3d', tr.make_c3d ?? true);
    this.setCheckbox('tri-remove-incomplete', tr.remove_incomplete_frames);
    this.setSelect('tri-fill-gaps', tr.fill_large_gaps_with ?? 'last_value');

    const f = t.filtering || {};
    this.setCheckbox('filt-enable', f.filter ?? true);
    this.setSelect('filt-type', f.type ?? 'butterworth');
    this.setCheckbox('filt-outliers', f.reject_outliers ?? true);
    this.setCheckbox('filt-display', f.display_figures);
    this.setCheckbox('filt-c3d', f.make_c3d ?? true);
    const bw = t.filtering?.butterworth || {};
    this.setVal('filt-bw-cutoff', bw.cut_off_frequency ?? 6.0);
    this.setVal('filt-bw-order', bw.order ?? 4);
    const km = t.filtering?.kalman || {};
    this.setVal('filt-kalman-trust', km.trust_ratio ?? 500);
    this.setCheckbox('filt-kalman-smooth', km.smooth ?? true);
    this.setVal('filt-gauss-sigma', (t.filtering?.gaussian || {}).sigma_kernel ?? 1);
    this.setVal('filt-loess-nb', (t.filtering?.loess || {}).nb_values_used ?? 5);
    this.setVal('filt-median-kernel', (t.filtering?.median || {}).kernel_size ?? 3);
    this.onFilterTypeChange();

    const ma = t.markerAugmentation || {};
    this.setCheckbox('viz-feet-floor', ma.feet_on_floor);
    this.setCheckbox('viz-c3d', ma.make_c3d ?? true);

    await this.loadTrcFiles();
  },

  // ─── Save Configs ───────────────────────────────────────────

  async saveProjectParams() {
    const fr = this.getVal('cfg-frame-rate'), frange = this.getVal('cfg-frame-range'), h = this.getVal('cfg-height');
    const res = await pywebview.api.save_config([
      ['project', 'multi_person', this.getCheckbox('cfg-multi-person')],
      ['project', 'frame_rate', fr === 'auto' ? 'auto' : parseInt(fr)],
      ['project', 'frame_range', frange],
      ['project', 'participant_height', h === 'auto' ? 'auto' : parseFloat(h)],
      ['project', 'participant_mass', parseFloat(this.getVal('cfg-mass'))],
    ]);
    this.flash(res);
  },

  async saveCalibrationConfig() {
    const res = await pywebview.api.save_config([
      ['calibration.calculate.intrinsics', 'intrinsics_corners_nb', [parseInt(this.getVal('cal-int-cols')), parseInt(this.getVal('cal-int-rows'))]],
      ['calibration.calculate.intrinsics', 'intrinsics_square_size', parseFloat(this.getVal('cal-int-square'))],
      ['calibration.calculate.intrinsics', 'extract_every_N_sec', parseFloat(this.getVal('cal-int-extract'))],
      ['calibration.calculate.intrinsics', 'intrinsics_extension', this.getSelect('cal-int-ext')],
      ['calibration.calculate.intrinsics', 'overwrite_intrinsics', this.getCheckbox('cal-int-overwrite')],
      ['calibration.calculate.intrinsics', 'show_detection_intrinsics', this.getCheckbox('cal-int-show')],
      ['calibration.calculate.extrinsics', 'extrinsics_method', this.getSelect('cal-ext-method')],
      ['calibration.calculate.extrinsics', 'extrinsics_extension', this.getSelect('cal-ext-ext')],
      ['calibration.calculate.extrinsics', 'show_reprojection_error', this.getCheckbox('cal-ext-reproj')],
      ['calibration.calculate', 'save_debug_images', this.getCheckbox('cal-debug-images')],
    ]);
    this.flash(res);
  },

  async savePoseConfig() {
    const res = await pywebview.api.save_config([
      ['pose', 'pose_model', this.getSelect('pose-model')],
      ['pose', 'mode', this.getSelect('pose-mode')],
      ['pose', 'backend', this.getSelect('pose-backend')],
      ['pose', 'device', this.getSelect('pose-device')],
      ['pose', 'det_frequency', parseInt(this.getVal('pose-det-freq'))],
      ['pose', 'tracking_mode', this.getSelect('pose-tracking')],
      ['pose', 'vid_img_extension', this.getSelect('pose-vid-ext')],
      ['pose', 'overwrite_pose', this.getCheckbox('pose-overwrite')],
      ['pose', 'display_detection', this.getCheckbox('pose-display')],
    ]);
    this.flash(res);
  },

  async saveSyncConfig() {
    const res = await pywebview.api.save_config([
      ['synchronization', 'approx_time_maxspeed', parseFloat(this.getVal('sync-peak-time'))],
      ['synchronization', 'time_range_around_maxspeed', parseFloat(this.getVal('sync-range'))],
      ['synchronization', 'filter_cutoff', parseFloat(this.getVal('sync-cutoff'))],
      ['synchronization', 'filter_order', parseInt(this.getVal('sync-order'))],
      ['synchronization', 'likelihood_threshold', parseFloat(this.getVal('sync-likelihood'))],
      ['synchronization', 'display_sync_plots', this.getCheckbox('sync-display')],
      ['synchronization', 'save_sync_plots', this.getCheckbox('sync-save')],
      ['synchronization', 'synchronization_gui', this.getCheckbox('sync-gui')],
    ]);
    this.flash(res);
  },

  async saveTriangConfig() {
    const res = await pywebview.api.save_config([
      ['triangulation', 'reproj_error_threshold_triangulation', parseFloat(this.getVal('tri-reproj'))],
      ['triangulation', 'likelihood_threshold_triangulation', parseFloat(this.getVal('tri-likelihood'))],
      ['triangulation', 'min_cameras_for_triangulation', parseInt(this.getVal('tri-min-cams'))],
      ['triangulation', 'interpolation', this.getSelect('tri-interp')],
      ['triangulation', 'interp_if_gap_smaller_than', parseInt(this.getVal('tri-max-gap'))],
      ['triangulation', 'make_c3d', this.getCheckbox('tri-c3d')],
      ['triangulation', 'remove_incomplete_frames', this.getCheckbox('tri-remove-incomplete')],
      ['triangulation', 'fill_large_gaps_with', this.getSelect('tri-fill-gaps')],
    ]);
    this.flash(res);
  },

  async saveFilterConfig() {
    const res = await pywebview.api.save_config([
      ['filtering', 'type', this.getSelect('filt-type')],
      ['filtering', 'reject_outliers', this.getCheckbox('filt-outliers')],
      ['filtering', 'display_figures', this.getCheckbox('filt-display')],
      ['filtering', 'make_c3d', this.getCheckbox('filt-c3d')],
      ['filtering.butterworth', 'cut_off_frequency', parseFloat(this.getVal('filt-bw-cutoff'))],
      ['filtering.butterworth', 'order', parseInt(this.getVal('filt-bw-order'))],
      ['filtering.kalman', 'trust_ratio', parseInt(this.getVal('filt-kalman-trust'))],
      ['filtering.kalman', 'smooth', this.getCheckbox('filt-kalman-smooth')],
      ['filtering.gaussian', 'sigma_kernel', parseInt(this.getVal('filt-gauss-sigma'))],
      ['filtering.loess', 'nb_values_used', parseInt(this.getVal('filt-loess-nb'))],
      ['filtering.median', 'kernel_size', parseInt(this.getVal('filt-median-kernel'))],
    ]);
    this.flash(res);
  },

  async saveVizConfig() {
    const res = await pywebview.api.save_config([
      ['markerAugmentation', 'feet_on_floor', this.getCheckbox('viz-feet-floor')],
      ['markerAugmentation', 'make_c3d', this.getCheckbox('viz-c3d')],
    ]);
    this.flash(res);
  },

  // ─── Pipeline Execution ─────────────────────────────────────

  _logTarget(stepName) {
    const processingSteps = ['poseEstimation', 'synchronization', 'triangulation', 'filtering'];
    if (processingSteps.includes(stepName)) return 'processing';
    if (stepName === 'calibration') return 'calibration';
    return 'visualization';
  },

  async runStep(stepName) {
    const target = this._logTarget(stepName);
    this.currentStepName = target;
    this._currentRunStep = stepName;
    const logEl = document.getElementById(`log-${target}`);
    if (logEl) logEl.innerHTML = '';
    const statusEl = document.getElementById(`run-status-${target}`);
    if (statusEl) { statusEl.textContent = 'Running...'; statusEl.className = 'run-status running'; }
    const progressEl = document.getElementById(`progress-${target}`);
    if (progressEl) { progressEl.style.width = '0%'; progressEl.classList.add('indeterminate'); }
    const abortEl = document.getElementById(`abort-${target}`);
    if (abortEl) abortEl.style.display = '';
    const result = await pywebview.api.run_step(stepName);
    if (!result.success) {
      this.appendLog(target, `[ERROR] ${result.error}`);
      if (statusEl) { statusEl.textContent = 'Failed'; statusEl.className = 'run-status error'; }
      if (progressEl) progressEl.classList.remove('indeterminate');
      this._currentRunStep = null;
      return;
    }
    this.startLogPoll(target);
  },

  async abortStep() { await pywebview.api.abort_step(); },

  _posePreviewTimer: null,
  _currentRunStep: null,

  startLogPoll(target) {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(async () => {
      const data = await pywebview.api.poll_logs();
      if (data.lines?.length) data.lines.forEach(l => this.appendLog(target, l));
      if (!data.running) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
        this.onStepFinished(target);
      }
    }, 250);

    // Start pose preview polling if running pose estimation
    if (this._currentRunStep === 'poseEstimation') {
      this._startPosePreview();
    }
  },

  _startPosePreview() {
    const wrap = document.getElementById('pose-preview-wrap');
    if (wrap) wrap.style.display = '';
    if (this._posePreviewTimer) clearInterval(this._posePreviewTimer);
    this._posePreviewTimer = setInterval(async () => {
      try {
        const res = await pywebview.api.get_pose_preview();
        if (res.success && res.image) {
          const img = document.getElementById('pose-preview-img');
          if (img) img.src = 'data:image/jpeg;base64,' + res.image;
        }
      } catch (e) {}
    }, 500);
  },

  _stopPosePreview() {
    if (this._posePreviewTimer) {
      clearInterval(this._posePreviewTimer);
      this._posePreviewTimer = null;
    }
  },

  async onStepFinished(target) {
    const progressEl = document.getElementById(`progress-${target}`);
    if (progressEl) { progressEl.classList.remove('indeterminate'); progressEl.style.width = '100%'; }
    const abortEl = document.getElementById(`abort-${target}`);
    if (abortEl) abortEl.style.display = 'none';
    const statusEl = document.getElementById(`run-status-${target}`);
    const logEl = document.getElementById(`log-${target}`);
    const txt = logEl ? logEl.textContent : '';
    if (txt.includes('[SUCCESS]')) {
      if (statusEl) { statusEl.textContent = 'Done'; statusEl.className = 'run-status done'; }
    } else {
      if (statusEl) { statusEl.textContent = 'Failed'; statusEl.className = 'run-status error'; }
    }
    // Stop pose preview
    this._stopPosePreview();
    this._currentRunStep = null;
    // Hide preview after short delay so user can see final frame
    setTimeout(() => {
      const wrap = document.getElementById('pose-preview-wrap');
      // Only hide if no longer running
      if (!this._running && wrap) wrap.style.display = 'none';
    }, 3000);

    await this.updateStepStatuses();
    if (target === 'calibration') await Calib.loadResults();
  },

  appendLog(target, line) {
    // Intercept [PROGRESS] lines from pose estimation
    if (line.startsWith('[PROGRESS]')) {
      const parts = line.substring(10).split('/');
      // format: current/total/videoName/vidIdx/totalVids/pct
      if (parts.length >= 6) {
        const [current, total, vidName, vidIdx, totalVids, pct] = parts;
        const info = document.getElementById('pose-preview-info');
        if (info) info.textContent = `${vidName} (${vidIdx}/${totalVids}) — Frame ${current}/${total}`;
        const bar = document.getElementById('pose-preview-bar');
        if (bar) bar.style.width = pct + '%';
        const progressEl = document.getElementById('progress-processing');
        if (progressEl) {
          progressEl.classList.remove('indeterminate');
          // Overall progress across all videos
          const overallPct = ((parseInt(vidIdx) - 1) / parseInt(totalVids) * 100 + parseInt(pct) / parseInt(totalVids));
          progressEl.style.width = Math.round(overallPct) + '%';
        }
      }
      return;  // Don't add progress lines to the console
    }

    const el = document.getElementById(`log-${target}`);
    if (!el) return;
    const span = document.createElement('span');
    if (line.includes('[ERROR]')) span.className = 'log-error';
    else if (line.includes('[SUCCESS]')) span.className = 'log-success';
    else if (line.includes('[WARNING]')) span.className = 'log-warning';
    else if (line.includes('[INFO]') || line.includes('[POSE_START]')) span.className = 'log-info';
    span.textContent = line + '\n';
    el.appendChild(span);
    el.scrollTop = el.scrollHeight;
  },

  // ─── Camera Videos ──────────────────────────────────────────

  async browseVideosDir() {
    const dir = await pywebview.api.browse_directory();
    if (dir) document.getElementById('pose-videos-dir').value = dir;
  },

  async refreshCameraVideos() { await this.loadCameraVideos(); },

  async loadCameraVideos() {
    const cfg = await pywebview.api.get_project_config();
    if (cfg.project_dir) document.getElementById('pose-videos-dir').value = cfg.project_dir + '/videos';
    const videos = await pywebview.api.list_camera_videos();
    const el = document.getElementById('camera-video-list');
    if (!videos?.length) { el.innerHTML = '<span class="file-missing">No videos found</span>'; return; }
    el.innerHTML = videos.map(cam => {
      const files = cam.files.length
        ? cam.files.map(f => `<span class="file-found">${f.split('/').pop()}</span>`).join('<br>')
        : '<span class="file-missing">No files</span>';
      return `<div class="cam-entry"><span class="cam-name">${cam.camera}</span><div class="cam-files">${files}</div></div>`;
    }).join('');
  },

  // ─── TRC Files ──────────────────────────────────────────────

  REQUIRED_MARKERS: [
    'Neck','RShoulder','LShoulder','RHip','LHip','RKnee','LKnee',
    'RAnkle','LAnkle','RHeel','LHeel','RSmallToe','LSmallToe',
    'RBigToe','LBigToe','RElbow','LElbow','RWrist','LWrist'
  ],

  async loadTrcFiles() {
    const files = await pywebview.api.list_trc_files();
    const sel = document.getElementById('viz-trc-select');
    if (!files?.length) {
      sel.innerHTML = '<option value="">No files found</option>';
      document.getElementById('viz-trc-info').style.display = 'none';
      document.getElementById('viz-trc-empty').style.display = '';
      return;
    }
    sel.innerHTML = '<option value="">Select a file...</option>' +
      files.map(f => `<option value="${f}">${f.split('/').pop()}</option>`).join('');
  },

  async onTrcSelected() {
    const path = document.getElementById('viz-trc-select').value;
    const infoEl = document.getElementById('viz-trc-info');
    const emptyEl = document.getElementById('viz-trc-empty');
    const section3d = document.getElementById('viz-3d-section');
    if (!path) {
      infoEl.style.display = 'none';
      emptyEl.style.display = '';
      section3d.style.display = 'none';
      return;
    }

    const info = await pywebview.api.read_trc_info(path);
    if (!info.success) { infoEl.style.display = 'none'; emptyEl.style.display = ''; return; }

    emptyEl.style.display = 'none';
    infoEl.style.display = '';
    document.getElementById('viz-trc-frames').innerHTML = `<strong>${info.num_frames}</strong> frames`;
    document.getElementById('viz-trc-rate').innerHTML = `<strong>${info.frame_rate}</strong> fps`;
    document.getElementById('viz-trc-units').innerHTML = `<strong>${info.num_markers}</strong> markers`;

    const markersEl = document.getElementById('viz-trc-markers');
    const req = new Set(this.REQUIRED_MARKERS);
    const found = new Set(info.markers);
    markersEl.innerHTML = info.markers.map(m => {
      const cls = req.has(m) ? 'marker-tag required' : 'marker-tag';
      return `<span class="${cls}">${m}</span>`;
    }).join('');
    const missing = this.REQUIRED_MARKERS.filter(m => !found.has(m));
    if (missing.length) {
      markersEl.innerHTML += missing.map(m => `<span class="marker-tag missing">${m}</span>`).join('');
    }

    // Load 3D data
    section3d.style.display = '';
    Viewer3D.loadTrc(path, info.frame_rate);
  },

  // ─── Filter Type Toggle ─────────────────────────────────────

  onFilterTypeChange() {
    const type = this.getSelect('filt-type');
    ['butterworth', 'kalman', 'gaussian', 'loess', 'median'].forEach(t => {
      const el = document.getElementById(`filt-${t}-params`);
      if (el) el.style.display = 'none';
    });
    const map = { butterworth: 'butterworth', butterworth_on_speed: 'butterworth', kalman: 'kalman', gaussian: 'gaussian', LOESS: 'loess', median: 'median' };
    const show = map[type];
    if (show) { const el = document.getElementById(`filt-${show}-params`); if (el) el.style.display = ''; }
  },

  // ─── Helpers ────────────────────────────────────────────────

  setVal(id, v) { const e = document.getElementById(id); if (e) e.value = v; },
  getVal(id) { const e = document.getElementById(id); return e ? e.value : ''; },
  setSelect(id, v) { const e = document.getElementById(id); if (e) e.value = v; },
  getSelect(id) { const e = document.getElementById(id); return e ? e.value : ''; },
  setCheckbox(id, v) { const e = document.getElementById(id); if (e) e.checked = !!v; },
  getCheckbox(id) { const e = document.getElementById(id); return e ? e.checked : false; },
  flash(res) { if (!res?.success) alert('Save failed: ' + (res?.error || 'Unknown')); },
};


// ═══════════════════════════════════════════════════════════════
// VIEWER3D — Three.js-based TRC marker viewer
// ═══════════════════════════════════════════════════════════════

const Viewer3D = {
  _scene: null,
  _camera: null,
  _renderer: null,
  _controls: null,
  _markers: [],       // marker names
  _frames: [],        // frame data from TRC
  _spheres: [],       // Three.js sphere meshes
  _bones: [],         // Three.js line objects for skeleton
  _currentFrame: 0,
  _playing: false,
  _playTimer: null,
  _fps: 30,
  _speed: 1,
  _initialized: false,

  // Skeleton connections (index pairs into marker array)
  // Will be computed dynamically based on marker names
  SKELETON_PAIRS: [
    ['Hip', 'RHip'], ['Hip', 'LHip'],
    ['RHip', 'RKnee'], ['RKnee', 'RAnkle'],
    ['RAnkle', 'RBigToe'], ['RAnkle', 'RSmallToe'], ['RAnkle', 'RHeel'],
    ['LHip', 'LKnee'], ['LKnee', 'LAnkle'],
    ['LAnkle', 'LBigToe'], ['LAnkle', 'LSmallToe'], ['LAnkle', 'LHeel'],
    ['Hip', 'Neck'], ['Neck', 'Head'], ['Head', 'Nose'],
    ['Neck', 'RShoulder'], ['RShoulder', 'RElbow'], ['RElbow', 'RWrist'],
    ['Neck', 'LShoulder'], ['LShoulder', 'LElbow'], ['LElbow', 'LWrist'],
  ],

  _initScene() {
    const container = document.getElementById('viewer-3d');
    if (!container) return;
    container.innerHTML = '';

    const w = container.clientWidth || 600;
    const h = container.clientHeight || 400;

    this._scene = new THREE.Scene();
    this._scene.background = new THREE.Color(0x050505);

    this._camera = new THREE.PerspectiveCamera(50, w / h, 0.01, 100);
    this._camera.position.set(2, 1.5, 3);
    this._camera.lookAt(0, 0.8, 0);

    this._renderer = new THREE.WebGLRenderer({ antialias: true });
    this._renderer.setSize(w, h);
    this._renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this._renderer.domElement);

    this._controls = new THREE.OrbitControls(this._camera, this._renderer.domElement);
    this._controls.target.set(0, 0.8, 0);
    this._controls.enableDamping = true;
    this._controls.dampingFactor = 0.08;
    this._controls.update();

    // Lights
    this._scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(3, 5, 3);
    this._scene.add(dir);

    // Grid
    const grid = new THREE.GridHelper(4, 20, 0x222222, 0x1a1a1a);
    this._scene.add(grid);

    // Axes
    const axes = new THREE.AxesHelper(0.3);
    this._scene.add(axes);

    this._animate();
    this._initialized = true;
  },

  _animate() {
    if (!this._renderer) return;
    requestAnimationFrame(() => this._animate());
    if (this._controls) this._controls.update();
    this._renderer.render(this._scene, this._camera);
  },

  resize() {
    const container = document.getElementById('viewer-3d');
    if (!container || !this._renderer) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    this._renderer.setSize(w, h);
    this._camera.aspect = w / h;
    this._camera.updateProjectionMatrix();
  },

  async loadTrc(path, fps) {
    this._fps = fps || 30;
    // Subsample: max ~500 frames for performance
    const info = await pywebview.api.read_trc_info(path);
    const totalFrames = info.num_frames || 100;
    const step = Math.max(1, Math.floor(totalFrames / 500));

    const data = await pywebview.api.read_trc_data(path, step);
    if (!data.success) return;

    this._markers = data.markers;
    this._frames = data.frames;
    this._currentFrame = 0;

    if (!this._initialized) this._initScene();
    this._buildMarkers();
    this._showFrame(0);

    const slider = document.getElementById('viewer-slider');
    slider.max = this._frames.length - 1;
    slider.value = 0;
    this._updateLabel();
  },

  _buildMarkers() {
    // Remove old
    this._spheres.forEach(s => this._scene.remove(s));
    this._bones.forEach(b => this._scene.remove(b));
    this._spheres = [];
    this._bones = [];

    // Create spheres for each marker
    const geo = new THREE.SphereGeometry(0.012, 12, 12);
    const colors = [0x0a84ff, 0x30d158, 0xff453a, 0xffd60a, 0xff9f0a, 0xbf5af2, 0x64d2ff, 0xac8e68];
    for (let i = 0; i < this._markers.length; i++) {
      const mat = new THREE.MeshStandardMaterial({ color: colors[i % colors.length], emissive: colors[i % colors.length], emissiveIntensity: 0.3 });
      const sphere = new THREE.Mesh(geo, mat);
      sphere.visible = false;
      this._scene.add(sphere);
      this._spheres.push(sphere);
    }

    // Build skeleton lines
    const markerIdx = {};
    this._markers.forEach((m, i) => markerIdx[m] = i);
    const lineMat = new THREE.LineBasicMaterial({ color: 0x444444, linewidth: 1 });
    for (const [a, b] of this.SKELETON_PAIRS) {
      if (a in markerIdx && b in markerIdx) {
        const geom = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
        const line = new THREE.Line(geom, lineMat);
        line.userData = { idxA: markerIdx[a], idxB: markerIdx[b] };
        line.visible = false;
        this._scene.add(line);
        this._bones.push(line);
      }
    }

    // Auto-fit camera to first frame
    if (this._frames.length > 0) {
      const pts = this._frames[0].p.filter(p => p[0] !== null);
      if (pts.length > 0) {
        const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        const cz = pts.reduce((s, p) => s + p[2], 0) / pts.length;
        this._controls.target.set(cx, cy, cz);
        this._camera.position.set(cx + 2, cy + 1, cz + 2.5);
        this._controls.update();
      }
    }
  },

  _showFrame(idx) {
    if (idx < 0 || idx >= this._frames.length) return;
    this._currentFrame = idx;
    const pts = this._frames[idx].p;

    for (let i = 0; i < this._spheres.length; i++) {
      const p = pts[i];
      if (p && p[0] !== null && !isNaN(p[0])) {
        this._spheres[i].position.set(p[0], p[1], p[2]);
        this._spheres[i].visible = true;
      } else {
        this._spheres[i].visible = false;
      }
    }

    // Update bones
    for (const line of this._bones) {
      const { idxA, idxB } = line.userData;
      const a = pts[idxA], b = pts[idxB];
      if (a && b && a[0] !== null && b[0] !== null && !isNaN(a[0]) && !isNaN(b[0])) {
        const pos = line.geometry.attributes.position;
        pos.setXYZ(0, a[0], a[1], a[2]);
        pos.setXYZ(1, b[0], b[1], b[2]);
        pos.needsUpdate = true;
        line.visible = true;
      } else {
        line.visible = false;
      }
    }

    document.getElementById('viewer-slider').value = idx;
    this._updateLabel();
  },

  _updateLabel() {
    const f = this._frames[this._currentFrame];
    const label = document.getElementById('viewer-frame-label');
    if (label && f) label.textContent = `Frame ${f.f} / ${this._frames[this._frames.length - 1]?.f || 0}`;
  },

  seekFrame(val) { this._showFrame(parseInt(val)); },
  nextFrame() { this._showFrame(Math.min(this._currentFrame + 1, this._frames.length - 1)); },
  prevFrame() { this._showFrame(Math.max(this._currentFrame - 1, 0)); },

  setSpeed(val) { this._speed = parseFloat(val); },

  togglePlay() {
    if (this._playing) {
      this._playing = false;
      clearInterval(this._playTimer);
      document.getElementById('viewer-play-btn').innerHTML = '&#9654; Play';
    } else {
      this._playing = true;
      document.getElementById('viewer-play-btn').innerHTML = '&#9646;&#9646; Pause';
      const interval = Math.max(10, (1000 / this._fps) / this._speed);
      this._playTimer = setInterval(() => {
        if (this._currentFrame >= this._frames.length - 1) {
          this._currentFrame = 0;
        } else {
          this._currentFrame++;
        }
        this._showFrame(this._currentFrame);
      }, interval);
    }
  },
};


// ═══════════════════════════════════════════════════════════════
// CALIB — In-window extrinsic calibration (replaces matplotlib)
// ═══════════════════════════════════════════════════════════════

const Calib = {
  _camIndex: 0,
  _totalCams: 0,
  _objCoords: [],     // 3D reference points from config
  _clickedPoints: [],  // 2D points for current camera
  _allCamData: [],     // all cameras' data
  _img: null,          // current camera image (HTMLImageElement)
  _imgW: 0,
  _imgH: 0,
  _canvas: null,
  _ctx: null,
  // Zoom/pan state
  _zoom: 1,
  _panX: 0,           // pan offset in image-pixel space
  _panY: 0,
  _isPanning: false,
  _panStartX: 0,
  _panStartY: 0,
  _panStartOfsX: 0,
  _panStartOfsY: 0,

  async startExtrinsic() {
    // Load 3D reference points
    const coordsResult = await pywebview.api.get_object_coords_3d();
    if (!coordsResult.success) { alert('Error: ' + coordsResult.error); return; }
    this._objCoords = coordsResult.coords;
    this._allCamData = [];
    this._camIndex = 0;

    // Show the clicker UI
    document.getElementById('calib-clicker').style.display = '';
    document.getElementById('btn-start-extrinsic').style.display = 'none';
    document.getElementById('btn-finish-calib').style.display = 'none';

    // Render 3D point list
    this._renderObjPtsList();

    // Load first camera
    await this._loadCamera(0);
  },

  async _loadCamera(idx) {
    this._camIndex = idx;
    this._clickedPoints = [];

    const result = await pywebview.api.get_extrinsic_frame(idx);
    if (!result.success) {
      alert('Error loading camera ' + idx + ': ' + result.error);
      return;
    }

    this._totalCams = result.total_cameras;
    this._imgW = result.width;
    this._imgH = result.height;

    // Update UI labels
    document.getElementById('calib-cam-label').textContent =
      `${result.cam_name} (${idx + 1} / ${result.total_cameras})`;
    this._updatePointCount();
    document.getElementById('calib-confirm-btn').disabled = true;

    // Load image
    this._img = new Image();
    this._img.onload = () => this._initCanvas();
    this._img.src = 'data:image/jpeg;base64,' + result.image;

    // Reset point list highlights
    this._renderObjPtsList();
  },

  _initCanvas() {
    this._canvas = document.getElementById('calib-canvas');
    const wrap = this._canvas.parentElement;
    const maxW = wrap.clientWidth;
    const scale = Math.min(maxW / this._imgW, 500 / this._imgH, 1);
    const dispW = Math.round(this._imgW * scale);
    const dispH = Math.round(this._imgH * scale);

    this._canvas.width = dispW;
    this._canvas.height = dispH;
    this._canvas.style.width = dispW + 'px';
    this._canvas.style.height = dispH + 'px';

    this._ctx = this._canvas.getContext('2d');

    // Reset zoom/pan
    this._zoom = 1;
    this._panX = 0;
    this._panY = 0;

    this._redraw();

    // Bind events
    this._canvas.onmousedown = (e) => this._onMouseDown(e);
    this._canvas.onmousemove = (e) => this._onMouseMove(e);
    this._canvas.onmouseup = (e) => this._onMouseUp(e);
    this._canvas.onmouseleave = (e) => this._onMouseUp(e);
    this._canvas.onwheel = (e) => { e.preventDefault(); this._onWheel(e); };
    this._canvas.oncontextmenu = (e) => { e.preventDefault(); return false; };
  },

  // Convert canvas pixel → image pixel, accounting for zoom/pan
  _canvasToImg(cx, cy) {
    const c = this._canvas;
    const baseScale = c.width / this._imgW;  // base fit scale
    const s = baseScale * this._zoom;
    // canvas center
    const centerX = c.width / 2;
    const centerY = c.height / 2;
    // image pixel
    const ix = (cx - centerX) / s + (this._imgW / 2) - this._panX;
    const iy = (cy - centerY) / s + (this._imgH / 2) - this._panY;
    return [ix, iy];
  },

  _onWheel(e) {
    const rect = this._canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Get image point under cursor before zoom
    const [ix, iy] = this._canvasToImg(mx, my);

    // Zoom
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const newZoom = Math.max(0.5, Math.min(20, this._zoom * factor));
    this._zoom = newZoom;

    // Adjust pan so the image point stays under cursor
    const c = this._canvas;
    const baseScale = c.width / this._imgW;
    const s = baseScale * this._zoom;
    const centerX = c.width / 2;
    const centerY = c.height / 2;
    this._panX = (this._imgW / 2) - ix + (mx - centerX) / s;
    this._panY = (this._imgH / 2) - iy + (my - centerY) / s;

    this._redraw();
    this._updateHint();
  },

  _onMouseDown(e) {
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      // Middle-click or Alt+left-click → pan
      this._isPanning = true;
      this._panStartX = e.clientX;
      this._panStartY = e.clientY;
      this._panStartOfsX = this._panX;
      this._panStartOfsY = this._panY;
      this._canvas.style.cursor = 'grabbing';
      return;
    }
    if (e.button === 2) {
      this.undoPoint();
      return;
    }
    if (e.button === 0) {
      this._placePoint(e);
    }
  },

  _onMouseMove(e) {
    if (!this._isPanning) return;
    const c = this._canvas;
    const baseScale = c.width / this._imgW;
    const s = baseScale * this._zoom;
    const dx = (e.clientX - this._panStartX) / s;
    const dy = (e.clientY - this._panStartY) / s;
    this._panX = this._panStartOfsX + dx;
    this._panY = this._panStartOfsY + dy;
    this._redraw();
  },

  _onMouseUp(e) {
    if (this._isPanning) {
      this._isPanning = false;
      this._canvas.style.cursor = 'crosshair';
    }
  },

  _placePoint(e) {
    if (this._clickedPoints.length >= this._objCoords.length) return;
    const rect = this._canvas.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const [ix, iy] = this._canvasToImg(cx, cy);
    // Clamp to image bounds
    if (ix < 0 || iy < 0 || ix > this._imgW || iy > this._imgH) return;
    this._clickedPoints.push([ix, iy]);
    this._updatePointCount();
    this._renderObjPtsList();
    this._redraw();
    document.getElementById('calib-confirm-btn').disabled = this._clickedPoints.length < 6;
  },

  _updateHint() {
    const hint = document.getElementById('calib-hint');
    if (hint) {
      const z = Math.round(this._zoom * 100);
      hint.textContent = `Scroll to zoom (${z}%) · Alt+drag to pan · Left-click to place · Right-click to undo`;
    }
  },

  // Convert image pixel → canvas pixel (inverse of _canvasToImg)
  _imgToCanvas(ix, iy) {
    const c = this._canvas;
    const baseScale = c.width / this._imgW;
    const s = baseScale * this._zoom;
    const centerX = c.width / 2;
    const centerY = c.height / 2;
    const cx = (ix - (this._imgW / 2) + this._panX) * s + centerX;
    const cy = (iy - (this._imgH / 2) + this._panY) * s + centerY;
    return [cx, cy];
  },

  _redraw() {
    if (!this._ctx || !this._img) return;
    const c = this._canvas;
    const ctx = this._ctx;
    const baseScale = c.width / this._imgW;
    const s = baseScale * this._zoom;
    const centerX = c.width / 2;
    const centerY = c.height / 2;

    // Clear canvas
    ctx.clearRect(0, 0, c.width, c.height);

    // Apply zoom/pan transform and draw image
    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.scale(s, s);
    ctx.translate(this._panX - this._imgW / 2, this._panY - this._imgH / 2);
    ctx.drawImage(this._img, 0, 0);
    ctx.restore();

    // Draw clicked points (in screen/canvas space)
    const crossSize = Math.max(8, 12 / this._zoom);  // shrink at high zoom
    this._clickedPoints.forEach((pt, i) => {
      const [x, y] = this._imgToCanvas(pt[0], pt[1]);
      // Crosshair
      ctx.strokeStyle = '#30d158';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x - crossSize, y); ctx.lineTo(x + crossSize, y);
      ctx.moveTo(x, y - crossSize); ctx.lineTo(x, y + crossSize);
      ctx.stroke();
      // Circle
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#30d158';
      ctx.fill();
      // Label
      ctx.fillStyle = '#30d158';
      ctx.font = '11px monospace';
      ctx.fillText(`${i + 1}`, x + crossSize + 3, y - 4);
    });

    // Draw next point guide (fixed at bottom of canvas, screen space)
    if (this._clickedPoints.length < this._objCoords.length) {
      const nextIdx = this._clickedPoints.length;
      const coord = this._objCoords[nextIdx];
      ctx.fillStyle = 'rgba(10,132,255,0.85)';
      ctx.font = '12px sans-serif';
      ctx.fillText(`Click point ${nextIdx + 1}: [${coord.join(', ')}]`, 10, c.height - 10);
    }
  },

  undoPoint() {
    if (this._clickedPoints.length === 0) return;
    this._clickedPoints.pop();
    this._updatePointCount();
    this._renderObjPtsList();
    this._redraw();
    document.getElementById('calib-confirm-btn').disabled = this._clickedPoints.length < 6;
  },

  _updatePointCount() {
    document.getElementById('calib-point-count').textContent =
      `${this._clickedPoints.length} / ${this._objCoords.length} points`;
  },

  _renderObjPtsList() {
    const list = document.getElementById('calib-objpts-list');
    list.innerHTML = this._objCoords.map((coord, i) => {
      let cls = 'calib-objpt';
      if (i < this._clickedPoints.length) cls += ' done';
      else if (i === this._clickedPoints.length) cls += ' active';
      return `<div class="${cls}"><span class="calib-objpt-dot"></span><span>${i + 1}. [${coord.join(', ')}]</span></div>`;
    }).join('');
  },

  async skipCamera() {
    // Skip this camera, move to next
    if (this._camIndex + 1 < this._totalCams) {
      await this._loadCamera(this._camIndex + 1);
    } else {
      this._finishClicking();
    }
  },

  async confirmCamera() {
    if (this._clickedPoints.length < 6) {
      alert('Need at least 6 points for calibration.');
      return;
    }

    // Store data for this camera
    const frame = await pywebview.api.get_extrinsic_frame(this._camIndex);
    this._allCamData.push({
      cam_index: this._camIndex,
      cam_name: frame.cam_name,
      points: [...this._clickedPoints],
    });

    App.appendLog('calibration', `[INFO] ${frame.cam_name}: ${this._clickedPoints.length} points confirmed`);

    // Move to next camera
    if (this._camIndex + 1 < this._totalCams) {
      await this._loadCamera(this._camIndex + 1);
    } else {
      this._finishClicking();
    }
  },

  _finishClicking() {
    document.getElementById('calib-clicker').style.display = 'none';
    document.getElementById('btn-start-extrinsic').style.display = 'none';
    document.getElementById('btn-finish-calib').style.display = '';

    App.appendLog('calibration', `[INFO] All cameras done. ${this._allCamData.length} cameras with points.`);
    App.appendLog('calibration', '[INFO] Click "Compute Calibration" to run solvePnP.');
  },

  async finishCalibration() {
    if (this._allCamData.length === 0) {
      alert('No calibration points collected. Click "Click Extrinsic Points" first.');
      return;
    }

    App.appendLog('calibration', '[INFO] Computing extrinsic calibration...');
    const statusEl = document.getElementById('run-status-calibration');
    if (statusEl) { statusEl.textContent = 'Computing...'; statusEl.className = 'run-status running'; }

    const result = await pywebview.api.run_calibration_with_points(this._allCamData);

    if (result.success) {
      App.appendLog('calibration', '[SUCCESS] Calibration saved to: ' + result.output_path);
      for (const cam of result.cameras) {
        if (cam.error) {
          App.appendLog('calibration', `[WARNING] ${cam.cam}: ${cam.error}`);
        } else {
          App.appendLog('calibration', `[INFO] ${cam.cam}: RMS reprojection error = ${cam.rms_px} px`);
        }
      }
      if (statusEl) { statusEl.textContent = 'Done'; statusEl.className = 'run-status done'; }
      await Calib.loadResults();  // load full results (intrinsics + extrinsics)
    } else {
      App.appendLog('calibration', '[ERROR] ' + result.error);
      if (statusEl) { statusEl.textContent = 'Failed'; statusEl.className = 'run-status error'; }
    }

    document.getElementById('btn-finish-calib').style.display = 'none';
    document.getElementById('btn-start-extrinsic').style.display = '';
    await App.updateStepStatuses();
  },

  showResults(data) {
    const card = document.getElementById('calib-results-card');
    const grid = document.getElementById('calib-results-grid');
    const summary = document.getElementById('calib-results-summary');
    if (!card || !grid) return;

    const intrinsics = data.intrinsics;
    const extrinsics = data.extrinsics;

    if (!intrinsics && !extrinsics) {
      card.style.display = 'none';
      return;
    }

    let html = '';
    const allRms = [];

    // Build per-camera combined view
    // Collect all camera names
    const camMap = {};  // cam_name → { int_rms, ext_rms, ext_error }
    if (intrinsics && intrinsics.cameras) {
      for (const c of intrinsics.cameras) {
        if (!camMap[c.cam]) camMap[c.cam] = {};
        camMap[c.cam].int_rms = c.rms_px;
      }
    }
    if (extrinsics && extrinsics.cameras) {
      for (const c of extrinsics.cameras) {
        if (!camMap[c.cam]) camMap[c.cam] = {};
        if (c.error) camMap[c.cam].ext_error = c.error;
        else camMap[c.cam].ext_rms = c.rms_px;
      }
    }

    for (const [cam, vals] of Object.entries(camMap)) {
      const hasInt = vals.int_rms !== undefined;
      const hasExt = vals.ext_rms !== undefined;
      const hasExtErr = vals.ext_error !== undefined;

      // Determine worst status for card color
      const worstRms = Math.max(vals.int_rms || 0, vals.ext_rms || 0);
      const cls = hasExtErr ? 'fail' : worstRms < 2 ? 'good' : worstRms < 5 ? 'warn' : 'bad';

      let rows = '';
      if (hasInt) {
        allRms.push(vals.int_rms);
        rows += `<div class="calib-result-row"><span class="calib-result-label">Intrinsic</span><span>${vals.int_rms.toFixed(3)} px</span></div>`;
      }
      if (hasExt) {
        allRms.push(vals.ext_rms);
        rows += `<div class="calib-result-row"><span class="calib-result-label">Extrinsic</span><span>${vals.ext_rms.toFixed(2)} px</span></div>`;
      }
      if (hasExtErr) {
        rows += `<div class="calib-result-row"><span class="calib-result-label">Extrinsic</span><span class="calib-result-err">${vals.ext_error}</span></div>`;
      }

      const mainRms = hasExt ? vals.ext_rms : hasInt ? vals.int_rms : null;
      const barW = mainRms !== null ? Math.min(100, (mainRms / 10) * 100) : 0;

      html += `<div class="calib-result-item ${cls}">
        <span class="calib-result-cam">${cam}</span>
        ${mainRms !== null
          ? `<span class="calib-result-value">${mainRms.toFixed(2)} <span class="calib-result-unit">px</span></span>`
          : `<span class="calib-result-value" style="font-size:13px">${vals.ext_error || '—'}</span>`}
        <div class="calib-result-bar"><div class="calib-result-bar-fill" style="width:${barW}%"></div></div>
        <div class="calib-result-details">${rows}</div>
      </div>`;
    }
    grid.innerHTML = html;

    if (allRms.length > 0) {
      const avg = allRms.reduce((a, b) => a + b, 0) / allRms.length;
      const max = Math.max(...allRms);
      const quality = avg < 1 ? 'Excellent' : avg < 2 ? 'Good' : avg < 5 ? 'Acceptable' : 'Poor — consider recalibrating';
      const ts = (extrinsics?.timestamp || intrinsics?.timestamp || '').replace('T', ' ').slice(0, 19);
      summary.innerHTML = `<strong>Mean:</strong> ${avg.toFixed(2)} px &nbsp;&bull;&nbsp; <strong>Max:</strong> ${max.toFixed(2)} px &nbsp;&bull;&nbsp; <strong>Quality:</strong> ${quality}` +
        (ts ? ` &nbsp;&bull;&nbsp; <span style="color:var(--text-3)">${ts}</span>` : '');
    } else {
      summary.textContent = 'No valid calibration results.';
    }

    card.style.display = '';
  },

  async loadResults() {
    try {
      const result = await pywebview.api.get_calibration_results();
      if (result.success && (result.intrinsics || result.extrinsics)) {
        this.showResults(result);
      } else {
        document.getElementById('calib-results-card').style.display = 'none';
      }
    } catch (e) {
      document.getElementById('calib-results-card').style.display = 'none';
    }
  },
};


// ─── Boot ─────────────────────────────────────────────────────
window.addEventListener('pywebviewready', () => App.init());
if (window.pywebview?.api) App.init();
window.addEventListener('resize', () => { if (Viewer3D._renderer) Viewer3D.resize(); });
