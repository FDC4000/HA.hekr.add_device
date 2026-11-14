"""End-to-end provision chain tests (against local mocks)."""
import http.server
import json
import unittest

from hekr_provision import provision

from ._util import http_server, make_jwt, mock_device, quiet

JWT = make_jwt("u-9")


def _cloud_handler(pin="Z9Y8X7"):
    @quiet
    class H(http.server.BaseHTTPRequestHandler):
        def _json(self, code, obj):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(obj).encode())

        def do_POST(self):  # noqa: N802  (UAA /login)
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            self._json(200, {"access_token": JWT, "refresh_token": "r"})

        def do_GET(self):  # noqa: N802  (USER /getPINCode)
            if self.headers.get("Authorization") != f"Bearer {JWT}":
                self._json(401, {}); return
            self._json(200, {"PINCode": pin})
    return H


class TestProvisionChain(unittest.TestCase):
    def test_full_softap_chain(self):
        with http_server(_cloud_handler("Z9Y8X7")) as base, mock_device("Z9Y8X7") as (h, p):
            res = provision.run(
                "+1", "accountpw", "MyWiFi", "wifipw",
                method="softap", uaa_base=base, user_base=base,
                softap_host=h, softap_port=p, attempts=3,
            )
        self.assertEqual(res["uid"], "u-9")
        self.assertEqual(res["pin"], "Z9Y8X7")
        self.assertTrue(res["provisioned"])
        self.assertEqual(res["device"]["devTid"], "ESP_TEST_0001")

    def test_smartconfig_method_builds_lengths(self):
        with http_server(_cloud_handler("Z9Y8X7")) as base:
            res = provision.run(
                "+1", "accountpw", "MyWiFi", "wifipw",
                method="smartconfig", uaa_base=base, user_base=base,
            )
        self.assertGreater(res["encoded_count"], 0)
        self.assertFalse(res["broadcast"])

    def test_skip_login_with_token(self):
        with http_server(_cloud_handler("Z9Y8X7")) as base:
            res = provision.run(
                None, None, "MyWiFi", "wifipw",
                method="smartconfig", access_token=JWT, user_base=base,
            )
        self.assertEqual(res["pin"], "Z9Y8X7")
        self.assertNotIn("uid", res)        # login was skipped

    def test_skip_pin(self):
        res = provision.run(
            None, None, "MyWiFi", "wifipw",
            method="smartconfig", access_token=JWT, pin="ABCDEF",
        )
        self.assertEqual(res["pin"], "ABCDEF")

    def test_missing_credentials_raises(self):
        with self.assertRaises(ValueError):
            provision.run(None, None, "MyWiFi", "wifipw", method="smartconfig")

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            provision.run(None, None, "MyWiFi", "wifipw",
                          method="bogus", access_token=JWT, pin="ABCDEF")


if __name__ == "__main__":
    unittest.main()
