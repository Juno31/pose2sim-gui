#!/usr/bin/env python3
"""
Markerless - Main Entry Point
A PyQt5-based GUI for the Pose2Sim pipeline
"""

import sys
import os


def check_environment():
    """
    Verify pose2sim is importable and print a precise, actionable error if not.
    Works correctly on Windows where CONDA_DEFAULT_ENV can be unreliable.
    """
    border = "=" * 60

    try:
        import Pose2Sim  # noqa: F401
    except ImportError:
        python_path = sys.executable
        conda_env   = os.environ.get("CONDA_DEFAULT_ENV", "(unknown)")

        print(f"\n{border}", file=sys.stderr)
        print("  Markerless -- pose2sim not found", file=sys.stderr)
        print(border, file=sys.stderr)
        print(f"\n  Python used  : {python_path}", file=sys.stderr)
        print(f"  Conda env    : {conda_env}", file=sys.stderr)
        print("", file=sys.stderr)

        if conda_env != "markerless":
            print("  The 'markerless' conda environment is not active.", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Fix:", file=sys.stderr)
            print("    conda activate markerless", file=sys.stderr)
            print("    python main.py", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Windows tip: use Anaconda Prompt or Miniforge Prompt,", file=sys.stderr)
            print("  NOT regular Command Prompt / PowerShell unless you", file=sys.stderr)
            print("  already ran 'conda init' for that shell.", file=sys.stderr)
        else:
            print("  pose2sim is not installed in the 'markerless' env.", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Fix:", file=sys.stderr)
            print("    conda activate markerless", file=sys.stderr)
            print("    pip install pose2sim", file=sys.stderr)

        print(f"\n{border}\n", file=sys.stderr)
        sys.exit(1)


def main():
    check_environment()

    from PyQt5.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Markerless")
    app.setOrganizationName("PerfAnalytics")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    qss_path = os.path.join(base_dir, "ui", "assets", "style.qss")
    with open(qss_path, "r") as f:
        app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
