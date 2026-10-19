"""Cloud rehearsal: observable, reproducible, entirely fictional data."""
from pathlib import Path
import tempfile
import unittest

from experiments.cloud_operations_rehearsal.run import run


class CloudPilotRehearsalTests(unittest.TestCase):
    def test_full_cloud_rehearsal_has_no_claim_of_real_customer_results(self):
        with tempfile.TemporaryDirectory() as location:
            folder = Path(location) / "ci-artifacts"
            result = run(folder)
            self.assertTrue(result["synthetic"])
            self.assertFalse(result["real_customer_pilot"])
            self.assertFalse(result["commercial_value_verified"])
            self.assertFalse(result["production_readiness_verified"])
            self.assertTrue(result["replayed_twice_identically"])
            self.assertEqual(result["workdays_replayed"], 10)
            self.assertTrue(result["midpoint_backup_restored"])
            self.assertTrue(result["backup_receipt_checked"])
            self.assertTrue(result["rma_reason_codes_optional"])
            self.assertEqual(result["source_reconciliation_states"][4], "CONFLICTED")
            self.assertEqual(result["source_reconciliation_states"][5], "VERIFIED")
            self.assertEqual(len(result["normalized_replay_sha256"]), 64)
            self.assertTrue((folder / "synthetic_rehearsal.json").is_file())
            self.assertTrue((folder / "synthetic_pilot.html").is_file())
            self.assertTrue((folder / "synthetic_last_brief.html").is_file())
            for p in folder.iterdir():
                content = p.read_text(encoding="utf-8")
                self.assertNotIn("CUSTOMER-REAL", content)
                self.assertNotIn("PERSONAL", content)


if __name__ == "__main__":
    unittest.main()
