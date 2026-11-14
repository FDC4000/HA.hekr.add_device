"""Tests for the AirKiss/SmartConfig length-encoder."""
import unittest

from hekr_provision import airkiss


class TestCRC8(unittest.TestCase):
    def test_known_vector(self):
        # Dallas/Maxim CRC-8 check value for "123456789"
        self.assertEqual(airkiss.crc8_maxim(b"123456789"), 0xA1)

    def test_empty(self):
        self.assertEqual(airkiss.crc8_maxim(b""), 0x00)


class TestEncoderStructure(unittest.TestCase):
    def setUp(self):
        self.ssid, self.pw, self.pin = "MyWiFi", "secret123", "A1B2C3"
        self.enc = airkiss.HekrAirKissEncoder(self.ssid, self.pw, self.pin)
        self.data = self.enc.get_encoded_data()

    def test_total_length_matches_formula(self):
        payload = len(self.pw) + len(self.pin)          # 15
        full, rem = divmod(payload, 4)                  # 3, 3
        seqs = full + (1 if rem else 0)                 # 4
        per_block = 4 + seqs * 6                         # prefix(4) + seq(6 each)
        per_frame = 200 + 80 + 15 * per_block           # leading + magic + 15 blocks
        self.assertEqual(len(self.data), 5 * per_frame)

    def test_leading_guide_code(self):
        self.assertEqual(self.data[:4], [1, 11, 21, 31])

    def test_magic_encodes_ssid_crc(self):
        off = airkiss.HekrAirKissEncoder.LEADING_REPEAT * 4
        m = self.data[off:off + 4]
        # low nibble of total length is stored in m[1] (| 0x10)
        total = len(self.ssid) + len(self.pw) + len(self.pin)
        self.assertEqual(m[1] & 0x0F, total & 0x0F)
        # m[2]/m[3] carry the high/low nibble of CRC8(ssid)
        crc = ((m[2] & 0x0F) << 4) | (m[3] & 0x0F)
        self.assertEqual(crc, airkiss.crc8_maxim(self.ssid.encode()))

    def test_value_ranges(self):
        self.assertGreaterEqual(min(self.data), 1)
        self.assertLessEqual(max(self.data), 383)       # ASCII data byte | 0x100

    def test_payload_roundtrip(self):
        # data bytes are the only values >= 256 (b | 0x100). Decode the first block.
        payload = len(self.pw) + len(self.pin)
        full, rem = divmod(payload, 4)
        n = (full + (1 if rem else 0)) * 4
        data_bytes = [v - 256 for v in self.data if v >= 256][:n]
        decoded = bytes(data_bytes).rstrip(b"\x00").decode()
        self.assertEqual(decoded, self.pw + self.pin)


if __name__ == "__main__":
    unittest.main()
