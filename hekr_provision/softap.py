#!/usr/bin/env python3
"""
Faithful Python reproduction of the Hekr/Wisen SoftAP provisioning exchange.

Source: me.hekr.hekrconfig.common.CommonDeviceConfig  (Wisen 1.9.1, jadx)
 - SoftAPAsyncTask.doInBackground / sendByTcp / sendByHttp
 - handlerConfigFromAP

FLOW (phone is joined to the device's own Wi-Fi AP):
  1. (cloud, with user Bearer token)  GET user-openapi.hekr.me/getPINCode?ssid=<ssid>  -> pinCode
  2. Every 1 s, send the plaintext line
         "ssid=<ssid>&password=<password>&pinCode=<pinCode>&end"
     to the device at 192.168.4.1:7001  (raw TCP; HTTP POST variant also exists)
  3. Device replies with ONE JSON line:
         {"action":"devConfig",
          "params":{"devTid":..,"STEP":<int>,"code":<int:200=ok>,"PIN":<pin>,"bind":<int>}}
  4. Accept only if   action=="devConfig"  AND  PIN == pinCode we sent  AND  bind != 0.
     code==200 => step ok (next STEP); code!=200 => step error.
     First accepted frame ends the TCP phase (Java sets received=true and the loop exits).
  5. (cloud) poll getNewDeviceList?pinCode=&ssid= -> device is bound to the account server-side.

SECURITY NOTE: ssid + Wi-Fi password + pinCode are transmitted in CLEARTEXT over
plain TCP/HTTP on 192.168.4.1:7001. Only run this against hardware you own/are
authorised to provision.
"""
from __future__ import annotations

import json
import socket
import time
from typing import Optional

DEFAULT_HOST = "192.168.4.1"
DEFAULT_PORT = 7001
SO_TIMEOUT = 5.0          # CommonDeviceConfig: socket.setSoTimeout(5000)
SEND_INTERVAL = 1.0       # Thread.sleep(1000) between attempts


# ---------------------------------------------------------------- payload ----
def build_payload(ssid: str, password: str, pin_code: str) -> str:
    """Exact string from SoftAPAsyncTask.doInBackground (no URL-encoding)."""
    return f"ssid={ssid}&password={password}&pinCode={pin_code}&end"


# --------------------------------------------------------- response parsing ---
def parse_dev_config(raw: str, expected_pin: str) -> Optional[dict]:
    """Reproduces handlerConfigFromAP(). Returns a normalised dict if the frame
    is a valid, PIN-matching, bound devConfig; otherwise None."""
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if obj.get("action") != "devConfig" or "params" not in obj:
        return None
    p = obj["params"]
    for key in ("devTid", "STEP", "code", "PIN", "bind"):
        if key not in p:
            return None
    if str(p["PIN"]) != str(expected_pin):   # TextUtils.equals(PIN, mPinCode)
        return None
    if int(p["bind"]) == 0:                    # bind == 0 -> rejected
        return None
    code = int(p["code"])
    return {
        "devTid": p["devTid"],
        "step": int(p["STEP"]),
        "code": code,
        "ok": code == 200,                     # code==200 -> next(step), else error(step,code)
        "bind": int(p["bind"]),
        "raw": obj,
    }


# -------------------------------------------------------------- transports ---
def send_by_tcp(payload: str, host: str, port: int, timeout: float = SO_TIMEOUT) -> Optional[str]:
    """sendByTcp(): open socket, write UTF-8 bytes, read ONE line back."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(payload.encode("utf-8"))
            # Java reads a single line via BufferedReader.readLine()
            buf = bytearray()
            while b"\n" not in buf and b"\r" not in buf:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf.extend(chunk)
            line = bytes(buf).splitlines()[0].decode("utf-8", "replace") if buf else ""
            return line or None
    except OSError:
        return None


def send_by_http(payload: str, host: str, port: int, timeout: float = SO_TIMEOUT) -> Optional[str]:
    """sendByHttp(): PostRequest to http://host:port with the same body."""
    import urllib.request
    try:
        req = urllib.request.Request(
            f"http://{host}:{port}", data=payload.encode("utf-8"), method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (local device)
            return resp.read().decode("utf-8", "replace").splitlines()[0]
    except Exception:
        return None


# ------------------------------------------------------------- orchestration -
def provision_softap(
    ssid: str,
    password: str,
    pin_code: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    transport: str = "tcp",
    max_attempts: int = 60,
    interval: float = SEND_INTERVAL,
) -> Optional[dict]:
    """Loop like SoftAPAsyncTask until a valid devConfig frame is received."""
    payload = build_payload(ssid, password, pin_code)
    send = send_by_tcp if transport == "tcp" else send_by_http
    for attempt in range(1, max_attempts + 1):
        resp = send(payload, host, port)
        if resp:
            parsed = parse_dev_config(resp, pin_code)
            if parsed:
                print(f"[{attempt:02d}] devConfig: devTid={parsed['devTid']} "
                      f"STEP={parsed['step']} code={parsed['code']} "
                      f"{'OK' if parsed['ok'] else 'ERROR'} bind={parsed['bind']}")
                return parsed            # first accepted frame ends the phase
            print(f"[{attempt:02d}] ignored response: {resp!r}")
        else:
            print(f"[{attempt:02d}] no response")
        time.sleep(interval)
    return None


# ---------------------------------------- optional: where the pinCode comes from
def get_pin_code(bearer_token: str, ssid: str,
                 base_url: str = "https://user-openapi.hekr.me/") -> Optional[str]:
    """GET getPINCode?ssid=<ssid> with Authorization: Bearer <token>.
    Returns the 6-char provisioning pinCode. Prefer hekr_provision.get_pincode
    for full error handling and region support."""
    import urllib.parse
    import urllib.request
    url = base_url + "getPINCode?ssid=" + urllib.parse.quote(ssid, safe="")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer_token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        body = resp.read().decode("utf-8", "replace")
    try:
        pin = json.loads(body).get("PINCode", "")   # field is "PINCode" (see getPinCode)
    except json.JSONDecodeError:
        return None
    return pin if len(pin) == 6 else None


# --------------------------------------------- mock device (for local testing) -
def _run_mock_device(host: str, port: int, pin_code: str, ready) -> None:
    """Minimal stand-in for the device's SoftAP listener on :7001.
    Parses the request line and answers one devConfig JSON line."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    ready.set()
    step = 0
    try:
        while True:
            conn, _ = srv.accept()
            with conn:
                data = conn.recv(4096).decode("utf-8", "replace")
                fields = dict(
                    kv.split("=", 1) for kv in data.replace("&end", "").split("&") if "=" in kv
                )
                step += 1
                reply = {
                    "action": "devConfig",
                    "params": {
                        "devTid": "ESP_TEST_0001",
                        "STEP": step,
                        "code": 200,
                        "PIN": fields.get("pinCode", ""),   # echo the pin the app sent
                        "bind": 1,
                    },
                }
                conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
            if step >= 1:
                break
    finally:
        srv.close()


if __name__ == "__main__":
    import threading

    SSID, PASSWORD, PIN = "MyWiFi", "secret123", "PIN12345"

    print("payload:", build_payload(SSID, PASSWORD, PIN))
    print()

    # Local loopback self-test against the mock device (no hardware needed).
    ready = threading.Event()
    t = threading.Thread(
        target=_run_mock_device, args=("127.0.0.1", 7001, PIN, ready), daemon=True
    )
    t.start()
    ready.wait(2.0)

    result = provision_softap(
        SSID, PASSWORD, PIN, host="127.0.0.1", port=7001, max_attempts=3
    )
    print("\nresult:", result and {k: result[k] for k in ("devTid", "step", "code", "ok", "bind")})

    # Real use: join the device AP, then
    #   provision_softap(ssid, password, pin_code)      # host defaults to 192.168.4.1:7001
    # where pin_code came from get_pin_code(<bearer>, ssid).
