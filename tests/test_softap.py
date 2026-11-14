"""Tests for the SoftAP exchange and response parsing."""
import json
import unittest

from hekr_provision import softap

from ._util import mock_device


class TestBuildPayload(unittest.TestCase):
    def test_exact_format(self):
        self.assertEqual(
            softap.build_payload("MyWiFi", "pw123", "A1B2C3"),
            "ssid=MyWiFi&password=pw123&pinCode=A1B2C3&end",
        )


class TestParseDevConfig(unittest.TestCase):
    def _frame(self, **over):
        p = {"devTid": "D1", "STEP": 1, "code": 200, "PIN": "A1B2C3", "bind": 1}
        p.update(over)
        return json.dumps({"action": "devConfig", "params": p})

    def test_valid(self):
        r = softap.parse_dev_config(self._frame(), "A1B2C3")
        self.assertEqual(r["devTid"], "D1")
        self.assertTrue(r["ok"])
        self.assertEqual(r["step"], 1)

    def test_pin_mismatch_rejected(self):
        self.assertIsNone(softap.parse_dev_config(self._frame(), "WRONG"))

    def test_bind_zero_rejected(self):
        self.assertIsNone(softap.parse_dev_config(self._frame(bind=0), "A1B2C3"))

    def test_code_not_200_is_not_ok(self):
        r = softap.parse_dev_config(self._frame(code=500), "A1B2C3")
        self.assertIsNotNone(r)
        self.assertFalse(r["ok"])

    def test_missing_field_rejected(self):
        bad = json.dumps({"action": "devConfig", "params": {"devTid": "D1"}})
        self.assertIsNone(softap.parse_dev_config(bad, "A1B2C3"))

    def test_wrong_action_rejected(self):
        bad = json.dumps({"action": "other", "params": {}})
        self.assertIsNone(softap.parse_dev_config(bad, "A1B2C3"))

    def test_non_json_rejected(self):
        self.assertIsNone(softap.parse_dev_config("not json", "A1B2C3"))


class TestProvisionSoftAP(unittest.TestCase):
    def test_against_mock_device(self):
        with mock_device("PIN999") as (host, port):
            r = softap.provision_softap(
                "MyWiFi", "wifipw", "PIN999",
                host=host, port=port, max_attempts=3,
            )
        self.assertIsNotNone(r)
        self.assertTrue(r["ok"])
        self.assertEqual(r["devTid"], "ESP_TEST_0001")

    def test_no_response_returns_none(self):
        # nothing listening on this port -> all attempts fail quickly
        r = softap.provision_softap(
            "MyWiFi", "wifipw", "PIN999",
            host="127.0.0.1", port=1, max_attempts=2, interval=0,
        )
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
