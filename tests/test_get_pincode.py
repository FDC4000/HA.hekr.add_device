"""Tests for fetching the provisioning pinCode."""
import http.server
import unittest

from hekr_provision import get_pincode

from ._util import http_server, quiet


def _handler(status, body, require_bearer="TOK"):
    @quiet
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if require_bearer and self.headers.get("Authorization") != f"Bearer {require_bearer}":
                self.send_response(401); self.end_headers(); self.wfile.write(b"{}"); return
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
    return H


class TestGetPinCode(unittest.TestCase):
    def test_success(self):
        with http_server(_handler(200, '{"PINCode":"A1B2C3"}')) as base:
            self.assertEqual(get_pincode.get_pin_code("TOK", "MyWiFi", base_url=base), "A1B2C3")

    def test_unauthorized(self):
        with http_server(_handler(200, '{"PINCode":"A1B2C3"}')) as base:
            with self.assertRaises(get_pincode.PinCodeError) as cm:
                get_pincode.get_pin_code("BAD", "MyWiFi", base_url=base)
            self.assertIn("401", str(cm.exception))

    def test_wrong_length_rejected(self):
        with http_server(_handler(200, '{"PINCode":"ABC"}')) as base:
            with self.assertRaises(get_pincode.PinCodeError):
                get_pincode.get_pin_code("TOK", "MyWiFi", base_url=base)

    def test_non_json_rejected(self):
        with http_server(_handler(200, "oops")) as base:
            with self.assertRaises(get_pincode.PinCodeError):
                get_pincode.get_pin_code("TOK", "MyWiFi", base_url=base)

    def test_regions_present(self):
        for r in ("asia", "america", "europe", "test"):
            self.assertIn("user-openapi", get_pincode.REGION_BASE[r])


if __name__ == "__main__":
    unittest.main()
