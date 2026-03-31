#!/usr/bin/env python3
"""
Markerless Web - PyWebView-based GUI for the Pose2Sim pipeline
"""

import sys
import os
import webview

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_environment():
    try:
        import Pose2Sim  # noqa: F401
    except ImportError:
        print("pose2sim not found. Run: pip install pose2sim", file=sys.stderr)
        sys.exit(1)


def main():
    check_environment()

    from app.api import Api

    api = Api()
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

    window = webview.create_window(
        "Markerless - Pose2Sim Pipeline",
        url=os.path.join(web_dir, "index.html"),
        js_api=api,
        width=1400,
        height=900,
        min_size=(1000, 700),
    )

    # Give api a reference to the window for file dialogs
    api._window = window

    webview.start(debug=False)


if __name__ == "__main__":
    main()
