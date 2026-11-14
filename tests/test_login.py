"""Tests for UAA login / token refresh."""
import http.server
import json
import unittest

from hekr_provision import login

from ._util import http_server, make_jwt, quiet

JWT = make_jwt("u-123")


def _handler(status=200, token=JWT):
    @quiet
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if status != 200:
                self.wfile.write(b'{"error":"bad"}'); return
            # echo back what identifies the path for assertions
            out = {"access_token": token, "refresh_token": "r-456", "_path": self.path,
                   "_body": body}
            self.wfile.write(json.dumps(out).encode())
    return H


class TestLogin(unittest.TestCase):
    def test_login_success_and_uid(self):
        with http_server(_handler()) as base:
            r = login.login("+10000000000", "pw", base_url=base)
        self.assertEqual(r["access_token"], JWT)
        self.assertEqual(r["refresh_token"], "r-456")
        self.assertEqual(r["uid"], "u-123")
        self.assertTrue(r["_path"].endswith("/login"))
        # body carries the expected fields
        self.assertEqual(r["_body"]["clientType"], "ANDROID")
        self.assertIn("appLoginInfo", r["_body"])

    def test_refresh(self):
        with http_server(_handler()) as base:
            r = login.refresh_token("r-456", base_url=base)
        self.assertEqual(r["access_token"], JWT)
        self.assertTrue(r["_path"].endswith("/token/refresh"))

    def test_http_error_raises(self):
        with http_server(_handler(status=400)) as base:
            with self.assertRaises(login.LoginError):
                login.login("+1", "pw", base_url=base)

    def test_decode_uid(self):
        self.assertEqual(login.decode_uid(JWT), "u-123")
        self.assertEqual(login.decode_uid("garbage"), "")


if __name__ == "__main__":
    unittest.main()
