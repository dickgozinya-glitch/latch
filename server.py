#!/usr/bin/env python3
"""Latch decision API. Zero third-party deps. python3 server.py"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from engine import decide, init_db, insert_mandate, load_mandate, load_seal, meter, verify_seal

HOST = os.environ.get("LATCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("LATCH_PORT", "8787"))
DB_PATH = os.environ.get("LATCH_DB", os.path.join(os.path.dirname(__file__), "latch.db"))
_lock = threading.Lock()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class Handler(BaseHTTPRequestHandler):
    server_version = "Latch/0.1"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def log_message(self, fmt: str, *args) -> None:
        print("[latch]", self.command, self.path, "-", fmt % args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        with _lock:
            conn = db()
            try:
                if path == "/health":
                    return self._json(200, {"ok": True, "service": "latch"})
                if path == "/v1/meter":
                    return self._json(200, meter(conn))
                if path.startswith("/v1/mandates/"):
                    mid = path.split("/")[-1]
                    row = load_mandate(conn, mid)
                    return self._json(200, row) if row else self._json(404, {"error": "mandate_not_found"})
                if path.startswith("/v1/seals/"):
                    sid = path.split("/")[-1]
                    row = load_seal(conn, sid)
                    return self._json(200, row) if row else self._json(404, {"error": "seal_not_found"})
                return self._json(404, {"error": "not_found"})
            finally:
                conn.close()

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            body = self._read()
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid_json"})
        with _lock:
            conn = db()
            try:
                if path == "/v1/mandates":
                    row = insert_mandate(conn, body)
                    return self._json(201, row)
                if path == "/v1/decisions":
                    result = decide(conn, body)
                    code = 200 if result["decision"] != "error" else 400
                    return self._json(code, result)
                if path.startswith("/v1/seals/") and path.endswith("/verify"):
                    sid = path.split("/")[-2]
                    return self._json(200, verify_seal(conn, sid))
                return self._json(404, {"error": "not_found"})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            finally:
                conn.close()


def main() -> None:
    conn = db()
    init_db(conn)
    conn.close()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Latch listening on http://{HOST}:{PORT}")
    print("POST /v1/mandates   POST /v1/decisions   GET /v1/meter")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
