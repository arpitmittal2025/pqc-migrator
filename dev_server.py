"""Local dev server: serves public/ and the same engine the Vercel function uses.

Run:  python dev_server.py        then open http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "api"))
from _engine import handle_json  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/api/analyze":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        status, body = handle_json(self.rfile.read(length) if length else b"{}")
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = partial(Handler, directory=str(ROOT / "public"))
    print(f"serving http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
