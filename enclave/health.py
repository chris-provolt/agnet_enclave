"""Tiny HTTP health endpoint served from a daemon thread (no curl needed)."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class HealthState:
    def __init__(self, role: str) -> None:
        self.role = role
        self.started = time.time()
        self.last_beat = time.time()
        self.status = "starting"
        self.detail: dict = {}

    def beat(self, status: str = "ok", **detail) -> None:
        self.last_beat = time.time()
        self.status = status
        if detail:
            self.detail.update(detail)

    def snapshot(self) -> dict:
        return {
            "role": self.role,
            "status": self.status,
            "uptime_s": round(time.time() - self.started, 1),
            "since_last_beat_s": round(time.time() - self.last_beat, 1),
            **self.detail,
        }


def serve_health(state: HealthState, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/health"):
                body = json.dumps(state.snapshot()).encode()
                stale = time.time() - state.last_beat > 300
                self.send_response(503 if stale or state.status == "error" else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args) -> None:  # silence default access log
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="health", daemon=True).start()
    return server
