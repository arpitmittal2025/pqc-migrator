"""Vercel serverless entry point: POST /api/analyze."""

from http.server import BaseHTTPRequestHandler
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine import handle_json  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        status, body = handle_json(raw)
        self._send(status, body)

    def do_GET(self) -> None:
        status, body = handle_json(json.dumps({"action": "samples"}))
        self._send(status, body)

    def log_message(self, *args) -> None:  # keep function logs quiet
        pass
