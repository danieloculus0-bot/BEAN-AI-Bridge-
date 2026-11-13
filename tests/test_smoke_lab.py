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
        report["phase"] = "python"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.sqlite"
            a = evaluate(report, "python", path, repetitions=7)
            b = evaluate(report, "python", path, repetitions=7)
            self.assertEqual(a["verdict"], "PASS")
            self.assertTrue(a["new_observation"])
            self.assertFalse(b["new_observation"])
            self.assertEqual(a["sha256"], b["sha256"])
    def test_phase_mismatch_never_enters_evidence_ledger(self):
        report = self.case({"package_install": "pass", "cli_smoke": "pass"})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.sqlite"
            with self.assertRaisesRegex(ValueError, "phase"):
                evaluate(report, "python", path)
            self.assertFalse(path.exists())

    def test_empty_required_gate_is_not_a_pass(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            assess(self.case(), ())

    def test_critical_boot_fails_if_vm_only_times_out(self):
        report = self.case({"package_install": "pass",
                            "boot_structure": "pass",
                            "guest_boot": "skip",
                            "first_run": "pass"})
        self.assertEqual(assess(report, ("package_install", "boot_structure", "guest_boot", "first_run"))["verdict"], "FAIL")
    def test_puppy_is_fail_closed_when_runtime_is_only_planned(self):
        from ezbean.smoke_lab import REQUIRED_PHASES
        self.assertEqual(len(REQUIRED_PHASES["puppy"]), 6)
        report = {"project": "venvwin", "phase": "puppy", "observed_at": NOW,
                  "checks": {
                      "kernel_source_guard": {"status": "pass", "evidence": "git:verified-source-sha"},
                      "lean_core_package_boundary": {"status": "pass", "evidence": "git:verified-package-lists"},
                      "runtime_overlay": {"status": "missing", "evidence": ""},
                      "ram_copy_verified": {"status": "unproven", "evidence": "only-config-present"},
                      "persistence_reboot": {"status": "missing", "evidence": ""},
                      "external_app_modules": {"status": "fail", "evidence": "apps-still-in-base"},
                  }}
        result = assess(report, REQUIRED_PHASES["puppy"])
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["passed"], 2)
        self.assertEqual(result["checks"]["runtime_overlay"]["status"], "missing")
        self.assertEqual(result["checks"]["ram_copy_verified"]["status"], "unproven")
        with tempfile.TemporaryDirectory() as d:
            receipt = evaluate(report, "puppy", Path(d) / "evidence.sqlite", repetitions=5)
            self.assertEqual(receipt["verdict"], "FAIL")
            self.assertEqual(receipt["repetitions"], 5)

    def test_actual_fail_preserved(self):
        result = assess(self.case({"package_install": "pass", "boot_structure": "fail"}), ("package_install", "boot_structure"))
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["passed"], 1)

if __name__ == "__main__":
    unittest.main()
