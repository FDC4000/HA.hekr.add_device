#!/usr/bin/env python3
"""
End-to-end device provisioning: login -> pinCode -> SoftAP / SmartConfig.

Chains the individual modules into one call, mirroring the app's flow:

    login.login(username, password)      -> access_token
    get_pincode.get_pin_code(token,ssid) -> 6-char pinCode
    softap.provision_softap(...)   OR    airkiss.HekrAirKissEncoder(...).broadcast()

Credential roles (do not confuse them):
  username / password        -> Hekr ACCOUNT login (UAA)
  ssid / wifi_password       -> the target Wi-Fi the DEVICE should join

Research / authorised testing only.
"""
from __future__ import annotations

from . import airkiss, get_pincode, login, softap


def run(
    username: str | None,
    password: str | None,
    ssid: str,
    wifi_password: str,
    *,
    pid: str = login.DEFAULT_PID,
    region: str = "asia",
    method: str = "softap",                 # "softap" | "smartconfig"
    # optional shortcuts (skip a step if already known):
    access_token: str | None = None,
    pin: str | None = None,
    # base-url overrides (default: derived from region):
    uaa_base: str | None = None,
    user_base: str | None = None,
    # softap options:
    softap_host: str = softap.DEFAULT_HOST,
    softap_port: int = softap.DEFAULT_PORT,
    transport: str = "tcp",
    attempts: int = 60,
    # smartconfig options:
    broadcast: bool = False,
    repeat: int = 1,
    sc_port: int = 7001,
    on_step=lambda msg: None,
) -> dict:
    """Run the full chain. Returns a summary dict; raises on login/pincode errors."""
    uaa_base = uaa_base or login.REGION_BASE[region]
    user_base = user_base or get_pincode.REGION_BASE[region]
    out: dict = {"method": method}

    # 1) login (unless a token was supplied)
    if access_token is None:
        if not username or not password:
            raise ValueError("username and password required (or pass access_token)")
        on_step("login: POST {UAA}/login ...")
        resp = login.login(username, password, pid=pid, base_url=uaa_base)
        access_token = resp["access_token"]
        out["uid"] = resp.get("uid", "")
        on_step(f"login: ok (uid={out['uid']})")
    out["access_token"] = access_token

    # 2) pinCode (unless supplied)
    if pin is None:
        on_step(f"pincode: GET getPINCode?ssid={ssid} ...")
        pin = get_pincode.get_pin_code(access_token, ssid, base_url=user_base)
        on_step(f"pincode: {pin}")
    out["pin"] = pin

    # 3) provision
    if method == "softap":
        on_step(f"softap: exchange with {softap_host}:{softap_port} ...")
        result = softap.provision_softap(
            ssid, wifi_password, pin,
            host=softap_host, port=softap_port, transport=transport, max_attempts=attempts,
        )
        out["provisioned"] = bool(result)
        out["device"] = result
        on_step("softap: " + ("device bound" if result else "no devConfig response"))
    elif method == "smartconfig":
        on_step("smartconfig: encoding packet lengths ...")
        enc = airkiss.HekrAirKissEncoder(ssid, wifi_password, pin)
        data = enc.get_encoded_data()
        out["encoded_count"] = len(data)
        if broadcast:
            on_step(f"smartconfig: broadcasting to 224.127.*.255:{sc_port} ...")
            airkiss.broadcast(data, port=sc_port, repeat=repeat)
            out["broadcast"] = True
        else:
            out["broadcast"] = False
        on_step(f"smartconfig: {len(data)} lengths ready")
    else:
        raise ValueError(f"unknown method: {method!r}")

    return out


# -------------------------------------------- local mock (for verification) ---
def _selftest() -> int:
    import base64
    import http.server
    import json
    import threading

    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    pl = base64.urlsafe_b64encode(b'{"uid":"u-123"}').rstrip(b"=").decode()
    jwt = f"{header}.{pl}.sig"

    class H(http.server.BaseHTTPRequestHandler):
        def _json(self, code, obj):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(obj).encode())

        def do_POST(self):  # noqa: N802  (UAA /login)
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            self._json(200, {"access_token": jwt, "refresh_token": "r-456"})

        def do_GET(self):  # noqa: N802  (USER /getPINCode)
            if self.headers.get("Authorization") != f"Bearer {jwt}":
                self._json(401, {}); return
            self._json(200, {"PINCode": "A1B2C3"})

        def log_message(self, *_):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"

    ev = threading.Event()
    threading.Thread(
        target=softap._run_mock_device, args=("127.0.0.1", 7001, "A1B2C3", ev), daemon=True
    ).start()
    ev.wait(2.0)

    try:
        res = run(
            "+10000000000", "accountpw", "MyWiFi", "wifipw",
            method="softap", uaa_base=base, user_base=base,
            softap_host="127.0.0.1", softap_port=7001, attempts=3,
            on_step=lambda m: print("  ·", m),
        )
        assert res["uid"] == "u-123" and res["pin"] == "A1B2C3" and res["provisioned"]
        print("selftest OK:", {k: res[k] for k in ("uid", "pin", "provisioned")})
        print("device:", res["device"] and {k: res["device"][k] for k in ("devTid", "step", "ok")})
        return 0
    finally:
        srv.shutdown()


if __name__ == "__main__":
    raise SystemExit(_selftest())
