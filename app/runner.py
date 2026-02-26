"""
core/runner.py - Background worker threads for pipeline execution
"""

import subprocess
import sys
import os
from PyQt5.QtCore import QThread, pyqtSignal


class PipelineWorker(QThread):
    """Runs a pose2sim pipeline step in a background thread."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)  # success, message

    def __init__(self, step_name: str, func, *args, **kwargs):
        super().__init__()
        self.step_name = step_name
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.log_signal.emit(f"[INFO] Starting {self.step_name}...")
            self.progress_signal.emit(10)
            self.func(*self.args, **self.kwargs)
            self.progress_signal.emit(100)
            self.log_signal.emit(f"[SUCCESS] {self.step_name} completed successfully.")
            self.finished_signal.emit(True, "")
        except Exception as e:
            # Emit the full traceback so nothing is hidden
            import traceback
            full = traceback.format_exc()
            for line in full.splitlines():
                self.log_signal.emit(f"[ERROR] {line}")
            self.finished_signal.emit(False, str(e))


class ScriptWorker(QThread):
    """Runs a Python script or shell command and streams output."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, cmd: list, cwd: str = None, env: dict = None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self._abort = False

    def abort(self):
        self._abort = True
        if hasattr(self, '_proc') and self._proc:
            self._proc.terminate()

    def run(self):
        try:
            self._proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                env=self.env,
            )
            for line in self._proc.stdout:
                if self._abort:
                    break
                line = line.rstrip()
                if line:
                    self.log_signal.emit(line)

            self._proc.wait()
            if self._proc.returncode == 0:
                self.log_signal.emit("[SUCCESS] Command finished successfully.")
                self.finished_signal.emit(True, "")
            else:
                msg = f"Process exited with code {self._proc.returncode}"
                self.log_signal.emit(f"[ERROR] {msg}")
                self.finished_signal.emit(False, msg)
        except Exception as e:
            self.log_signal.emit(f"[ERROR] {str(e)}")
            self.finished_signal.emit(False, str(e))
