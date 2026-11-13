#!/usr/bin/env python3
"""Unified CLI for the hekr_provision toolkit.

Usage (run from the toolkit's parent directory):
    python3 -m hekr_provision.cli smartconfig --ssid MyWiFi --password secret123 --pin A1B2C3
    python3 -m hekr_provision.cli softap      --ssid MyWiFi --password secret123 --pin PIN12345
    python3 -m hekr_provision.cli pincode     --token <bearer> --ssid MyWiFi

Only use against hardware you own / are authorised to provision. Credentials are
sent in cleartext in the SoftAP/SmartConfig channels (see README).
"""
from __future__ import annotations

import argparse
import sys

from . import airkiss, get_pincode, login, softap


def _cmd_smartconfig(a: argparse.Namespace) -> int:
    enc = airkiss.HekrAirKissEncoder(a.ssid, a.password, a.pin)
    data = enc.get_encoded_data()
    print(f"encoded packet-length count : {len(data)}")
    print(f"value range                 : {min(data)}..{max(data)}")
    print(f"first 12                    : {data[:12]}")
    if a.send:
        print(f"broadcasting to 224.127.*.255:{a.port} ...")
        airkiss.broadcast(data, port=a.port, repeat=a.repeat)
        print("done.")
    return 0


def _cmd_softap(a: argparse.Namespace) -> int:
    result = softap.provision_softap(
        a.ssid, a.password, a.pin,
        host=a.host, port=a.port,
        transport="http" if a.http else "tcp",
        max_attempts=a.attempts,
    )
    if result:
        print("\nPROVISIONED:", {k: result[k] for k in ("devTid", "step", "code", "ok", "bind")})
        return 0
    print("\nno valid devConfig response received", file=sys.stderr)
    return 1


def _cmd_login(a: argparse.Namespace) -> int:
    base = a.base_url or login.REGION_BASE[a.region]
    try:
        if a.refresh:
            resp = login.refresh_token(a.refresh, base_url=base)
        else:
            resp = login.login(a.username, a.password, pid=a.pid, base_url=base)
    except login.LoginError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(resp["access_token"])
    return 0


def _cmd_pincode(a: argparse.Namespace) -> int:
    try:
        pin = get_pincode.get_pin_code(a.token, a.ssid, base_url=a.base_url)
    except get_pincode.PinCodeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(pin)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hekr_provision", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("login", help="authenticate to Hekr UAA; print access_token")
    lg.add_argument("--username", help="phone/email/account")
    lg.add_argument("--password", help="password")
    lg.add_argument("--pid", default=login.DEFAULT_PID, help="product id / pit")
    lg.add_argument("--region", choices=sorted(login.REGION_BASE), default="asia")
    lg.add_argument("--base-url", help="override BASE_UAA_URL (wins over --region)")
    lg.add_argument("--refresh", help="refresh an existing refresh_token instead of logging in")
    lg.set_defaults(func=_cmd_login)

    sc = sub.add_parser("smartconfig", help="build/broadcast AirKiss packet lengths")
    sc.add_argument("--ssid", required=True)
    sc.add_argument("--password", required=True)
    sc.add_argument("--pin", required=True)
    sc.add_argument("--send", action="store_true", help="actually UDP-broadcast the lengths")
    sc.add_argument("--port", type=int, default=7001)
    sc.add_argument("--repeat", type=int, default=1)
    sc.set_defaults(func=_cmd_smartconfig)

    sa = sub.add_parser("softap", help="exchange with device at 192.168.4.1:7001")
    sa.add_argument("--ssid", required=True)
    sa.add_argument("--password", required=True)
    sa.add_argument("--pin", required=True)
    sa.add_argument("--host", default=softap.DEFAULT_HOST)
    sa.add_argument("--port", type=int, default=softap.DEFAULT_PORT)
    sa.add_argument("--http", action="store_true", help="use HTTP POST instead of raw TCP")
    sa.add_argument("--attempts", type=int, default=60)
    sa.set_defaults(func=_cmd_softap)

    pc = sub.add_parser("pincode", help="fetch provisioning pinCode from the cloud")
    pc.add_argument("--token", required=True, help="user Bearer access_token")
    pc.add_argument("--ssid", required=True)
    pc.add_argument("--base-url", default="https://user-openapi.hekr.me/")
    pc.set_defaults(func=_cmd_pincode)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
