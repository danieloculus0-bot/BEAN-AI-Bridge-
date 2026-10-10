"""BEAN bridge smoke lab must not accept absent or fabricated pass markers."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ezbean.smoke_lab import assess, evaluate

NOW = "2026-10-10T07:00:00+00:00"

class SmokeLabTests(unittest.TestCase):
    def case(self, statuses=None):
        statuses = statuses or {}
        return {"project": "venvwin", "phase": "iso", "observed_at": NOW,
                "checks": {name: {"status": status, "evidence": "sha256:known-build-artifact"}
                           for name, status in statuses.items()}}
    def test_fail_closed_without_evidence(self):
        result = assess(self.case({"package_install": "pass"}), ("package_install", "boot_structure"))
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["checks"]["boot_structure"]["status"], "missing")
    def test_no_unproven_pass(self):
        report = self.case({"guest_boot": "pass"})
        report["checks"]["guest_boot"]["evidence"] = ""
        self.assertEqual(assess(report, ("guest_boot",))["checks"]["guest_boot"]["status"], "unproven")
    def test_replay_and_idempotency(self):
        report = self.case({"package_install": "pass", "cli_smoke": "pass"})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.sqlite"
            a = evaluate(report, "python", path, repetitions=7)
            b = evaluate(report, "python", path, repetitions=7)
            self.assertEqual(a["verdict"], "PASS")
            self.assertTrue(a["new_observation"])
            self.assertFalse(b["new_observation"])
            self.assertEqual(a["sha256"], b["sha256"])
    def test_critical_boot_fails_if_vm_only_times_out(self):
        report = self.case({"package_install": "pass",
                            "boot_structure": "pass",
                            "guest_boot": "skip",
                            "first_run": "pass"})
        self.assertEqual(assess(report, ("package_install", "boot_structure", "guest_boot", "first_run"))["verdict"], "FAIL")
    def test_actual_fail_preserved(self):
        result = assess(self.case({"package_install": "pass", "boot_structure": "fail"}), ("package_install", "boot_structure"))
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["passed"], 1)

if __name__ == "__main__":
    unittest.main()
