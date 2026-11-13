#!/usr/bin/env python3
"""
Fetch the device-provisioning pinCode from the Hekr cloud.

Faithful reproduction of HekrUserAction.getPinCode() (Wisen 1.9.1, jadx):

    GET {BASE_USER_URL}getPINCode?ssid=<url-encoded ssid>
        Authorization: Bearer <access_token>
    -> 200  {"PINCode": "<exactly 6 chars>"}

The response field is "PINCode" (note the capitalisation) and the app rejects any
value whose length != 6. The access_token is the user's login access_token
(JWT from POST {UAA}/login); if it is expired the real app calls
POST {UAA}/token/refresh first.

Research / authorised testing only.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

# BASE_USER_URL per region (ConstantsUtil.UrlUtil / setDomain)
REGION_BASE = {
    "asia":    "https://user-openapi.hekr.me/",
    "america": "https://user-openapi.hekrus.me/",
    "europe":  "https://user-openapi.hekreu.me/",
    "test":    "https://test-user-openapi.hekr.me/",
}
DEFAULT_BASE = REGION_BASE["asia"]


class PinCodeError(Exception):
    """Raised when the pinCode cannot be obtained or is invalid."""


def get_pin_code(access_token: str, ssid: str,
                 base_url: str = DEFAULT_BASE, timeout: float = 10.0) -> str:
    """Return the 6-char provisioning pinCode for the given ssid, or raise."""
    url = base_url + "getPINCode?ssid=" + urllib.parse.quote(ssid, safe="")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code == 401:
            raise PinCodeError(
                "401 Unauthorized — access_token expired/invalid; "
                "refresh it via POST {UAA}/token/refresh"
            ) from e
        raise PinCodeError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise PinCodeError(f"network error: {e.reason}") from e

    try:
        pin = json.loads(body).get("PINCode", "")
    except json.JSONDecodeError:
        raise PinCodeError(f"non-JSON response: {body!r}") from None
    if len(pin) != 6:                       # app check: empty or length != 6 -> fail
        raise PinCodeError(f"invalid pinCode (expected 6 chars, got {len(pin)}): {pin!r}")
    return pin


# ------------------------------------------------------------------- CLI ------
def _main(argv=None) -> int:
    import argparse
    import os

    p = argparse.ArgumentParser(description="Fetch the Hekr provisioning pinCode.")
    p.add_argument("--ssid", required=True, help="target Wi-Fi SSID")
    p.add_argument("--token", default=os.environ.get("HEKR_TOKEN"),
                   help="user Bearer access_token (or set HEKR_TOKEN)")
    p.add_argument("--region", choices=sorted(REGION_BASE), default="asia")
    p.add_argument("--base-url", help="override BASE_USER_URL (wins over --region)")
    p.add_argument("--selftest", action="store_true",
                   help="run against a local mock server (no token/network needed)")
    a = p.parse_args(argv)

    if a.selftest:
        return _selftest()

    if not a.token:
        p.error("no token given (use --token or HEKR_TOKEN)")

    base = a.base_url or REGION_BASE[a.region]
    try:
        print(get_pin_code(a.token, a.ssid, base_url=base))
        return 0
    except PinCodeError as e:
        print(f"error: {e}", file=__import__("sys").stderr)
        return 1


# -------------------------------------------- local mock (for verification) ---
def _selftest() -> int:
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.headers.get("Authorization", "") != "Bearer TESTTOKEN":
                self.send_response(401); self.end_headers(); self.wfile.write(b"{}"); return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"PINCode":"A1B2C3"}')

        def log_message(self, *_):  # silence
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    try:
        pin = get_pin_code("TESTTOKEN", "MyWiFi", base_url=base)
        print(f"selftest OK: pinCode={pin}")
        # also verify the 401 path
        try:
            get_pin_code("WRONG", "MyWiFi", base_url=base)
        except PinCodeError as e:
            print(f"selftest OK: 401 handled -> {str(e).splitlines()[0]}")
        return 0
    finally:
        srv.shutdown()


if __name__ == "__main__":
    raise SystemExit(_main())
