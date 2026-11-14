"""Smoke tests for the CLI dispatcher (offline paths only)."""
import contextlib
import io
import unittest

from hekr_provision import cli


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = cli.main(argv)
    return rc, out.getvalue()


class TestCLI(unittest.TestCase):
    def test_smartconfig_offline(self):
        rc, out = _run(["smartconfig", "--ssid", "X", "--password", "Y", "--pin", "ABC123"])
        self.assertEqual(rc, 0)
        self.assertIn("encoded packet-length count", out)

    def test_subcommands_registered(self):
        parser = cli.build_parser()
        # argparse stores subparser choices
        sub = next(a for a in parser._actions if hasattr(a, "choices") and a.choices
                   and "provision" in a.choices)
        self.assertEqual(
            set(sub.choices), {"provision", "login", "pincode", "smartconfig", "softap"}
        )

    def test_missing_required_arg_errors(self):
        # argparse exits with code 2 on missing required --ssid
        with self.assertRaises(SystemExit) as cm:
            _run(["smartconfig", "--password", "Y", "--pin", "ABC123"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
