#!/usr/bin/env python3
"""
Faithful Python port of me.hekr.hekrconfig.utils.HekrAirKissEncoder
(Wisen / Hekr-Hummingbird 1.9.1, decompiled with jadx).

WHAT IT IS
----------
A SmartConfig/AirKiss-style encoder. It does NOT build a data packet; it builds
a list of *UDP-packet LENGTHS*. The provisioning code sends dummy UDP datagrams
whose BYTE LENGTH equals each produced integer, to multicast 224.127.<n>.255:7001.
A device in Wi-Fi monitor mode measures those frame lengths and reconstructs the
credentials. (See CommonDeviceConfig.sendMsgToDevice / DatagramPacket(buf, len,...)).

Constructor arg order mirrors the Java: HekrAirKissEncoder(ssid, password, pinCode)
 - ssid     -> only its CHAR LENGTH and CRC8 go into the "magic code"
               (the SSID string itself is NOT transmitted; the device matches
                the CRC8 against the APs it can see)
 - password + pinCode  -> the actual payload that is length-encoded

Value ranges let the receiver classify each length:
  leading   : 1, 11, 21, 31
  magic     : 0x00|n, 0x10|n, 0x20|n, 0x30|n     (1..63)
  prefix    : 0x40|n, 0x50|n, 0x60|n, 0x70|n     (64..127)
  seq crc   : crc | 0x80                          (128..255)
  seq index : index | 0x80                        (128..)
  data byte : byte | 0x100                        (256..383 for ASCII)

NOTE: like the original, this only behaves well for ASCII SSID/password/pinCode.
"""
from __future__ import annotations
from typing import List


def crc8_maxim(data: bytes) -> int:
    """Dallas/Maxim CRC-8, poly 0x8C (reflected 0x31), init 0x00.
    Exact reproduction of HekrAirKissEncoder.CRC8(byte[])."""
    crc = 0
    for byte in data:
        b = byte & 0xFF
        for _ in range(8):
            mix = (crc ^ b) & 1
            crc = (crc >> 1) & 0xFF
            if mix:
                crc ^= 0x8C          # = 140 = TwitterAuthConfig.DEFAULT_AUTH_REQUEST_CODE
            b >>= 1
    return crc & 0xFF


class HekrAirKissEncoder:
    OUTER_REPEAT = 5                 # outer while-loop: i = 5,4,3,2,1
    BLOCK_REPEAT = 15                # inner for-loop i3 < 15
    LEADING_REPEAT = 50              # leadingPart: 50 x [1,11,21,31]
    MAGIC_REPEAT = 20                # magicCode: 20 x 4 nibbles

    def __init__(self, ssid: str, password: str, pin_code: str, charset: str = "utf-8"):
        self.ssid = ssid
        self.password = password
        self.pin_code = pin_code
        self._cs = charset
        self._out: List[int] = []
        self._build()

    # --- public API (mirrors getEncodedData()) ---
    def get_encoded_data(self) -> List[int]:
        return list(self._out)

    # --- internals ---
    def _append(self, v: int) -> None:
        self._out.append(v)

    def _leading_part(self) -> None:
        guide = (1, 11, 21, 31)
        for _ in range(self.LEADING_REPEAT):
            for g in guide:
                self._append(g)

    def _magic_code(self) -> None:
        # length = len(password) + len(pinCode) + len(ssid)   (char counts)
        length = len(self.password) + len(self.pin_code) + len(self.ssid)
        m = [0, 0, 0, 0]
        m[0] = (length >> 4) & 15
        if m[0] == 0:
            m[0] = 8
        m[1] = (length & 15) | 16
        crc = crc8_maxim(self.ssid.encode(self._cs))
        m[2] = 32 | ((crc >> 4) & 15)
        m[3] = (crc & 15) | 48
        for _ in range(self.MAGIC_REPEAT):
            for v in m:
                self._append(v)

    def _prefix_code(self) -> None:
        # prefixCode(password): encodes password length + CRC8 of that length byte
        length = len(self.password)
        crc = crc8_maxim(bytes([length & 0xFF]))
        p = [
            ((length >> 4) & 15) | 64,
            (length & 15) | 80,
            ((crc >> 4) & 15) | 96,
            (crc & 15) | 112,
        ]
        for v in p:
            self._append(v)

    def _sequence(self, index: int, four: bytes) -> None:
        # four is exactly 4 bytes (zero padded for the final chunk)
        buf = bytes([index & 0xFF]) + four          # index followed by 4 data bytes
        self._append(crc8_maxim(buf) | 128)          # CRC of (index+data) | 0x80
        self._append((index & 0xFF) | 128)           # index marker | 0x80
        for b in four:                               # each data byte | 0x100
            sb = b if b < 128 else b - 256           # Java signed-byte semantics
            self._append(sb | 256)                   # Python | matches Java two's-complement

    def _build(self) -> None:
        data = (self.password + self.pin_code).encode(self._cs)   # str4 = str2 + str3
        full = len(data) // 4
        rem = len(data) % 4
        for _ in range(self.OUTER_REPEAT):
            self._leading_part()
            self._magic_code()
            for _ in range(self.BLOCK_REPEAT):
                self._prefix_code()
                for i in range(full):
                    self._sequence(i, data[i * 4:i * 4 + 4])
                if rem != 0:
                    chunk = data[full * 4:] + bytes(4 - rem)       # zero-pad to 4
                    self._sequence(full, chunk)


# ---- optional: actually transmit (as the app does) ----
def broadcast(encoded: List[int], port: int = 7001, repeat: int = 1, gap: float = 0.004) -> None:
    """Send dummy UDP datagrams of the given LENGTHS to 224.127.<n>.255:port.
    Only run on a network where you are authorised to provision a device."""
    import socket, time
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    for _ in range(repeat):
        for n, length in enumerate(encoded):
            if length <= 0:
                continue
            group = f"224.127.{n & 0xFF}.255"       # app derives group from the index
            try:
                s.sendto(b"\x00" * length, (group, port))
            except OSError:
                pass
            time.sleep(gap)
    s.close()


if __name__ == "__main__":
    enc = HekrAirKissEncoder(ssid="Baumhaus", password="20HungerBieberRaketeFeuer", pin_code="A1B2C3")
    data = enc.get_encoded_data()

    # CRC8 self-check: Maxim CRC-8 of b"123456789" == 0xA1
    assert crc8_maxim(b"123456789") == 0xA1, "CRC8 mismatch"

    print(f"total encoded lengths : {len(data)}")
    print(f"leading (first 8)     : {data[:8]}")
    off = enc.LEADING_REPEAT * 4
    print(f"magic code (4)        : {data[off:off+4]}")
    off2 = off + enc.MAGIC_REPEAT * 4
    print(f"first prefix code (4) : {data[off2:off2+4]}")
    print(f"first sequence (6)    : {data[off2+4:off2+10]}")
    print(f"value range           : min={min(data)} max={max(data)}")
