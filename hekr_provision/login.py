#!/usr/bin/env python3
"""
Log in to the Hekr UAA service and obtain an access_token / refresh_token.

Faithful reproduction of me.hekr.sdk.HekrUser.login() / refreshToken()
(Wisen 1.9.1, jadx):

    POST {BASE_UAA_URL}login
        Content-Type: application/json , Accept: application/json
        {"username","password","pit":<pid>,"clientType":"ANDROID","appLoginInfo":{...}}
    -> {"access_token": <JWT>, "refresh_token": ..., ...}

    POST {BASE_UAA_URL}token/refresh
        {"refresh_token": <stored>}
    -> {"access_token", "refresh_token", ...}

The access_token is a JWT; its base64 payload carries "uid" (see refreshUserInfo).
`pit` is the product id (HekrSDK.getPid()), read in the app from res/raw/config.json
Hekr.AppId — the bundled Wisen value is the placeholder "00000000000".

Research / authorised testing only.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

# BASE_UAA_URL per region (me.hekr.sdk.Constants.UrlUtil / setDomain)
REGION_BASE = {
    "asia":    "https://uaa-openapi.hekr.me/",
    "america": "https://uaa-openapi.hekrus.me/",
    "europe":  "https://uaa-openapi.hekreu.me/",
    "test":    "https://test-uaa-openapi.hekr.me/",
}
DEFAULT_BASE = REGION_BASE["asia"]
DEFAULT_PID = "00000000000"          # Wisen config.json Hekr.AppId (placeholder)


class LoginError(Exception):
    """Raised when login or token refresh fails."""


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise LoginError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise LoginError(f"network error: {e.reason}") from e
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise LoginError(f"non-JSON response: {body!r}") from None


def _default_app_login_info() -> dict:
    """appLoginInfo device fingerprint (getLoginInfo()). Values are placeholders;
    override for a specific device profile."""
    return {
        "id": "0000000000000000",     # AppIdUtil.getAppId() (Android ID)
        "osVersion": "11",             # OsUtil.getSystemVersion()
        "type": "generic",             # OsUtil.getSystemModel()
        "appVersion": "1.9.1",         # AppVersionUtil.getVerName()
        "name": "Wisen",               # AppUtil.getAppName()
    }


def decode_uid(access_token: str) -> str:
    """Extract 'uid' from the JWT payload (base64 middle segment)."""
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)          # pad
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("uid", "")
    except (IndexError, ValueError, json.JSONDecodeError):
        return ""


def login(username: str, password: str, pid: str = DEFAULT_PID,
          base_url: str = DEFAULT_BASE, app_login_info: dict | None = None,
          timeout: float = 15.0) -> dict:
    """Return {'access_token','refresh_token','uid', ...} or raise LoginError."""
    payload = {
        "username": username,
        "password": password,
        "pit": pid,
        "clientType": "ANDROID",
        "appLoginInfo": app_login_info or _default_app_login_info(),
    }
    resp = _post_json(base_url + "login", payload, timeout)
    if "access_token" not in resp:
        raise LoginError(f"no access_token in response: {resp!r}")
    resp.setdefault("uid", decode_uid(resp["access_token"]))
    return resp


def refresh_token(refresh: str, base_url: str = DEFAULT_BASE,
                  timeout: float = 15.0) -> dict:
    """POST token/refresh with a stored refresh_token."""
    resp = _post_json(base_url + "token/refresh", {"refresh_token": refresh}, timeout)
    if "access_token" not in resp:
        raise LoginError(f"no access_token in refresh response: {resp!r}")
    resp.setdefault("uid", decode_uid(resp["access_token"]))
    return resp


# ------------------------------------------------------------------- CLI ------
def _main(argv=None) -> int:
    import argparse
    import os
    import sys

    p = argparse.ArgumentParser(description="Log in to Hekr UAA; print the access_token.")
    p.add_argument("--username", help="phone/email/account")
    p.add_argument("--password", default=os.environ.get("HEKR_PASSWORD"),
                   help="password (or set HEKR_PASSWORD)")
    p.add_argument("--pid", default=DEFAULT_PID, help="product id / pit")
    p.add_argument("--region", choices=sorted(REGION_BASE), default="asia")
    p.add_argument("--base-url", help="override BASE_UAA_URL (wins over --region)")
    p.add_argument("--refresh", help="refresh an existing refresh_token instead of logging in")
    p.add_argument("--json", action="store_true", help="print the full JSON response")
    p.add_argument("--selftest", action="store_true", help="run against a local mock server")
    a = p.parse_args(argv)

    if a.selftest:
        return _selftest()

    base = a.base_url or REGION_BASE[a.region]
    try:
        if a.refresh:
            resp = refresh_token(a.refresh, base_url=base)
        else:
            if not a.username or not a.password:
                p.error("--username and --password (or HEKR_PASSWORD) required")
            resp = login(a.username, a.password, pid=a.pid, base_url=base)
    except LoginError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print(resp["access_token"])
    return 0


# -------------------------------------------- local mock (for verification) ---
def _selftest() -> int:
    import http.server
    import threading

    # a tiny JWT with {"uid":"u-123"} payload
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    pl = base64.urlsafe_b64encode(b'{"uid":"u-123"}').rstrip(b"=").decode()
    jwt = f"{header}.{pl}.sig"

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            ok = self.path.endswith("/login") and body.get("username") and body.get("pit")
            ok = ok or (self.path.endswith("/token/refresh") and body.get("refresh_token"))
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            out = {"access_token": jwt, "refresh_token": "r-456"} if ok else {"error": "bad"}
            self.wfile.write(json.dumps(out).encode())

        def log_message(self, *_):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    try:
        r = login("+10000000000", "pw", base_url=base)
        assert r["access_token"] == jwt and r["uid"] == "u-123"
        print(f"selftest OK: login -> uid={r['uid']} refresh={r['refresh_token']}")
        r2 = refresh_token(r["refresh_token"], base_url=base)
        assert r2["access_token"] == jwt
        print("selftest OK: token/refresh -> access_token renewed")
        return 0
    finally:
        srv.shutdown()


if __name__ == "__main__":
    raise SystemExit(_main())
