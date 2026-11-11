"""Installed BEAN Operations pilot diagnostic checks."""
import json
import tempfile
import unittest
from pathlib import Path

from ezbean.backup import backup
from ezbean.doctor import inspect
from ezbean.operations_run import make_demo_exports, run, DEFAULT_DEMO_AS_OF
from ezbean.pilot import record


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_no_sources_never_falsely_claims_green(self):
        x = inspect()
        self.assertFalse(x["all_requested_checks_pass"])
        self.assertFalse(x["production_certified"])
        self.assertEqual(x["database"]["state"], "not_checked")
        self.assertNotIn("password", json.dumps(x).lower())

    def test_local_ledger_backup_and_trial_are_diagnosed_without_raw_records(self):
        export_dir = make_demo_exports(self.root / "fictional")
        data = self.root / "site.sqlite"
        page = self.root / "morning.html"
        run(database=data, exports=export_dir, out=page, site="DEMO_ONLY",
            start="2026-10-01", as_of=DEFAULT_DEMO_AS_OF, synthetic=True)
        saved = self.root / "backup.sqlite"
        backup(data, saved)
        pilot = self.root / "pilot.jsonl"
        record(pilot, page.with_suffix(".json"), day="2026-10-16",
               baseline_minutes=15, bean_minutes=12,
               confirmed_useful=1, false_alerts=0, missed_issues=0)
        status = inspect(database=data, backup=saved, pilot=pilot)
        self.assertTrue(status["all_requested_checks_pass"])
        self.assertEqual(status["database"]["snapshot_count"], 3)
        self.assertTrue(status["backup"]["receipt_verified"])
        self.assertEqual(status["pilot"]["workdays_recorded"], 1)
        self.assertFalse(status["pilot"]["pilot_complete"])
        self.assertFalse(status["production_certified"])
        self.assertNotIn("FICTIONAL-001", json.dumps(status))
        self.assertNotIn("EXAMPLE ONLY", json.dumps(status))

    def test_deleted_receipt_or_missing_db_is_visible(self):
        data = self.root / "site.sqlite"
        saved = self.root / "backup.sqlite"
        self.assertEqual(inspect(database=data)["database"]["state"], "fail")
        self.assertEqual(inspect(backup=saved)["backup"]["state"], "fail")
        self.assertFalse(inspect(backup=saved)["all_requested_checks_pass"])


if __name__ == "__main__":
    unittest.main()
