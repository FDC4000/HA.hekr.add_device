"""Shared test helpers: ephemeral mock HTTP server + device-AP launcher."""
from __future__ import annotations

import base64
import contextlib
import http.server
import json
import threading

from hekr_provision import softap


def make_jwt(uid: str = "u-123") -> str:
    """Build a minimal unsigned JWT whose payload carries {"uid": uid}."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"uid": uid}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


@contextlib.contextmanager
def http_server(handler_cls):
    """Run `handler_cls` on an ephemeral 127.0.0.1 port; yield its base URL."""
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/"
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)


@contextlib.contextmanager
def mock_device(pin: str, host: str = "127.0.0.1", port: int = 7001):
    """Run softap._run_mock_device (serves one connection, echoes the pin)."""
    ready = threading.Event()
    t = threading.Thread(
        target=softap._run_mock_device, args=(host, port, pin, ready), daemon=True
    )
    t.start()
    ready.wait(2.0)
    try:
        yield (host, port)
    finally:
        t.join(timeout=2)


def quiet(handler_cls):
    """Silence a BaseHTTPRequestHandler subclass's logging."""
    handler_cls.log_message = lambda *a, **k: None
    return handler_cls
