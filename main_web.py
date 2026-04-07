#!/usr/bin/env python3
"""
Markerless Web - PyWebView-based GUI for the Pose2Sim pipeline
"""

import sys
import os
import threading
import webview
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_environment():
    try:
        import Pose2Sim  # noqa: F401
    except ImportError:
        print("pose2sim not found. Run: pip install pose2sim", file=sys.stderr)
        sys.exit(1)


def _start_media_server():
    """Start a local HTTP server on a random port to serve video files."""
    class CORSHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, base_path="/", **kwargs):
            self._base_path = base_path
            super().__init__(*args, **kwargs)

        def translate_path(self, path):
            # Serve from root filesystem, but only files under allowed paths
            import urllib.parse
            path = urllib.parse.unquote(path)
            # Remove leading slash
            if path.startswith('/'):
                path = path[1:]
            return '/' + path

        def do_GET(self):
            import urllib.parse
            path = urllib.parse.unquote(self.path)
            if path.startswith('/'):
                path = path[1:]
            full_path = '/' + path
            if not os.path.isfile(full_path):
                self.send_error(404, "File not found")
                return
            # Only serve video files
            if not full_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                self.send_error(403, "Forbidden")
                return
            # Support range requests for video seeking
            file_size = os.path.getsize(full_path)
            range_header = self.headers.get('Range')
            if range_header:
                import re as _re
                start, end = 0, file_size - 1
                m = _re.match(r'bytes=(\d+)-(\d*)', range_header)
                if m:
                    start = int(m.group(1))
                    if m.group(2):
                        end = int(m.group(2))
                length = end - start + 1
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                self.send_header('Content-Length', str(length))
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(full_path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(remaining, 65536))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('Content-Length', str(file_size))
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(full_path, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)

        def log_message(self, format, *args):
            pass  # Silence logs

    server = TCPServer(('127.0.0.1', 0), CORSHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return port


def main():
    check_environment()

    from app.api import Api

    media_port = _start_media_server()
    api = Api()
    api._media_port = media_port
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
