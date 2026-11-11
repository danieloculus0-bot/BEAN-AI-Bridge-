"""Single-command BEAN Operations beta: local sources, fictional trial, receipts."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ezbean.operations_run import make_demo_exports, run, DEFAULT_DEMO_AS_OF
from ezbean.pilot import record, load_log, report


class OperationsRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exports = make_demo_exports(self.root / "exports")
        self.database = self.root / "private" / "evidence.sqlite"
        self.out = self.root / "private" / "brief.html"

    def test_single_command_demo_is_real_package_pipeline_not_fake_report(self):
        result = run(
            database=self.database, exports=self.exports, out=self.out,
            site="DEMO_ONLY", start="2026-10-01",
            as_of=DEFAULT_DEMO_AS_OF, synthetic=True,
        )
        self.assertTrue(result["synthetic"])
        self.assertFalse(result["actual_business_validation"])
        self.assertEqual(len(result["source_status"]), 3)
        self.assertTrue(all(x["status"] == "imported" for x in result["source_status"]))
        brief = json.loads(self.out.with_suffix(".json").read_text())
        self.assertEqual(brief["metrics"]["rma_observed"]["value"], 1)
        self.assertEqual(brief["metrics"]["shipment_line_otd"]["value"], 100.0)
        self.assertEqual(brief["metrics"]["past_due_open_job_lines"]["value"], 1)
        self.assertNotIn(
            "RMA_REASON_MISSING", {x["code"] for x in brief["exceptions"]}
        )
        self.assertIn("FICTIONAL DEMONSTRATION", self.out.read_text())
        receipt = json.loads(self.out.with_suffix(".receipt.json").read_text())
        self.assertEqual(receipt["schema"], "BEAN_OPERATIONAL_RUN_RECEIPT_V1")
        self.assertEqual(receipt["open_exceptions"], brief["open_exception_count"])
        self.assertEqual(len(receipt["json_sha256"]), 64)
        self.assertNotIn("FICTIONAL-001", self.out.read_text())
        self.assertNotIn("FICTIONAL-001", self.out.with_suffix(".json").read_text())

    def test_idempotent_reimport_is_detected_and_brief_does_not_drift(self):
        first = run(
            database=self.database, exports=self.exports, out=self.out,
            site="DEMO_ONLY", start="2026-10-01",
            as_of=DEFAULT_DEMO_AS_OF, synthetic=True,
        )
        second = run(
            database=self.database, exports=self.exports, out=self.out,
            site="DEMO_ONLY", start="2026-10-01",
            as_of=DEFAULT_DEMO_AS_OF, synthetic=True,
        )
        self.assertTrue(all(x["status"] == "duplicate" for x in second["source_status"]))
        self.assertEqual(first["json_sha256"], second["json_sha256"])

    def test_rejected_export_does_not_publish_new_brief(self):
        self.exports.joinpath(
            "Shipment Summary - Detail Report - 2026-10-16T120000.000.csv"
        ).write_text("not,a,report\nvery,bad,report\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "could not be ingested"):
            run(database=self.database, exports=self.exports, out=self.out,
                site="DEMO_ONLY", start="2026-10-01",
                as_of=DEFAULT_DEMO_AS_OF)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.with_suffix(".receipt.json").exists())

    def test_pilot_saves_only_review_aggregates_not_raw_source(self):
        run(database=self.database, exports=self.exports, out=self.out,
            site="DEMO_ONLY", start="2026-10-01",
            as_of=DEFAULT_DEMO_AS_OF, synthetic=True)
        path = self.root / "private" / "pilot.jsonl"
        saved = record(path, self.out.with_suffix(".json"),
                       day="2026-10-16", baseline_minutes=30, bean_minutes=20,
                       confirmed_useful=1, false_alerts=0, missed_issues=0)
        self.assertEqual(saved["day"], "2026-10-16")
        self.assertEqual(report(load_log(path))["minutes_saved"], 10.0)
        self.assertNotIn("FICTIONAL-001", path.read_text())


if __name__ == "__main__":
    unittest.main()
