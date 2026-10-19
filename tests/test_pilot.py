"""Local pilot evidence ledger tests. No live ERP or personal information."""
import json
from pathlib import Path
import tempfile
import unittest

from ezbean.daily_brief import SCHEMA
from ezbean.pilot import load_log, record, report, render_html


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.log = self.base / "private" / "pilot.jsonl"
        self.brief = self.base / "brief.json"

    def sample(self, *, site="SITE_A", count=3):
        self.brief.write_text(json.dumps({
            "schema": SCHEMA, "site": site,
            "as_of": "2026-10-19T12:00:00+00:00",
            "open_exception_count": count,
            # Raw source values must NEVER be copied to our trial ledger.
            "raw_sensitive_source": "CUSTOMER-SENTINEL-999",
        }), encoding="utf-8")

    def write(self, day, **overrides):
        params = dict(day=day, baseline_minutes=30, bean_minutes=18,
                      confirmed_useful=2, false_alerts=1, missed_issues=0)
        params.update(overrides)
        return record(self.log, self.brief, **params)

    def test_ten_workday_pilot_retains_results_and_measures_time(self):
        self.sample()
        for day in range(1, 11):
            self.write(f"2026-10-{day:02}")
        saved = load_log(self.log)
        self.assertEqual(len(saved), 10)
        self.assertEqual(saved[-1]["previous_sha256"], saved[-2]["record_sha256"])
        summary = report(saved)
        self.assertTrue(summary["pilot_complete"])
        self.assertEqual(summary["workdays_recorded"], 10)
        self.assertEqual(summary["baseline_minutes"], 300)
        self.assertEqual(summary["bean_minutes"], 180)
        self.assertEqual(summary["minutes_saved"], 120)
        self.assertEqual(summary["time_reduction_percent"], 40)
        self.assertEqual(summary["confirmed_useful"], 20)
        self.assertEqual(summary["false_alerts"], 10)
        self.assertEqual(summary["missed_issues"], 0)
        self.assertNotIn("CUSTOMER-SENTINEL-999", self.log.read_text())
        self.assertNotIn("CUSTOMER-SENTINEL-999", render_html(summary))

    def test_short_pilot_never_declares_complete(self):
        self.sample()
        self.write("2026-10-19")
        self.assertFalse(report(load_log(self.log))["pilot_complete"])

    def test_duplicate_workday_cannot_be_silently_overwritten(self):
        self.sample()
        self.write("2026-10-19")
        with self.assertRaisesRegex(ValueError, "already recorded"):
            self.write("2026-10-19")
        self.assertEqual(len(load_log(self.log)), 1)

    def test_invalid_adjudication_is_not_written(self):
        self.sample(count=3)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            self.write("2026-10-19", confirmed_useful=3, false_alerts=1)
        with self.assertRaisesRegex(ValueError, "finite"):
            self.write("2026-10-19", bean_minutes=float("nan"))
        self.assertFalse(self.log.exists())

    def test_hash_chain_catches_mutations_and_resume_preserves_research(self):
        self.sample()
        self.write("2026-10-19")
        self.write("2026-10-20")
        lines = self.log.read_text().splitlines()
        tampered = json.loads(lines[0])
        tampered["baseline_minutes"] = 480
        lines[0] = json.dumps(tampered)
        self.log.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "continuity mismatch"):
            load_log(self.log)
        with self.assertRaisesRegex(ValueError, "continuity mismatch"):
            self.write("2026-10-21")

    def test_reopen_and_report_separate_sites(self):
        self.sample(site="SITE_A")
        self.write("2026-10-19")
        self.sample(site="SITE_B")
        self.write("2026-10-19")
        self.assertEqual(report(load_log(self.log), site="SITE_A")["workdays_recorded"], 1)
        self.assertEqual(report(load_log(self.log))["workdays_recorded"], 2)
        self.assertFalse(report(load_log(self.log))["pilot_complete"])


if __name__ == "__main__":
    unittest.main()
