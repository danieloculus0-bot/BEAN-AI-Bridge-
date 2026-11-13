"""Synthetic-only Daily Exception Brief reliability and privacy regressions."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ezbean.daily_brief import SCHEMA, build_daily_brief, render_html, main
from ezbean.jobboss_exports import ExportSponge
from ezbean.management_intelligence import analyze_site


def raw(*, as_of="2026-10-10T12:00:00Z", days="verified", shipping=10,
        reconciled=10, quarantine=0, rma=2, missing_schedule=0, include_ship=True):
    return {
        "schema": "BEAN_JOBBOSS_EXPORT_V1",
        "window_start": "2026-10-01",
        "as_of": as_of,
        "metrics": {
            "otd_percent_by_shipment_line": 70.0 if include_ship else None,
            "shipment_lines": shipping if include_ship else None,
            "on_time_shipment_lines": 7 if include_ship else None,
            "partially_shipped_lines": 1 if include_ship else None,
            "past_due_open_job_lines": None if missing_schedule else 3,
            "schedule_due_date_lines": 5,
            "schedule_missing_shipped_quantity_lines": missing_schedule,
            "rma_entries": rma,
            "rma_missing_reason_entries": 1,
            "rma_quantity": None,
            "rma_cost_usd": None,
        },
        "source_verification": {"shipment_days_early_late": {
            "status": days, "reconciled_lines": reconciled,
            "conflicting_lines": 1 if days == "conflicted" else 0
        }},
        "quarantined_rma_rows": [{"row_ref": "CUSTOMER-123-PRIVATE", "issue": "sensitive"}] * quarantine,
        "rma_reason_counts": {"SENSITIVE CUSTOMER DEFECT TEXT": rma},
        "evidence": {"shipment_row_refs": ["SHOULD-NEVER-ESCAPE"],
                     "past_due_row_refs": ["JOB-SECRET-77"]},
    }


def summary(**kwargs):
    return analyze_site("SITE_A", raw(**kwargs))


class BriefTests(unittest.TestCase):
    def test_fresh_verified_metrics_and_sorted_review_queue(self):
        brief = build_daily_brief(summary())
        self.assertEqual(brief["schema"], SCHEMA)
        self.assertEqual(brief["metrics"]["shipment_line_otd"]["value"], 70.0)
        self.assertEqual(brief["metrics"]["past_due_open_job_lines"]["value"], 3)
        self.assertEqual(brief["metrics"]["rma_quantity"]["value"], None)
        self.assertIsNone(brief["metrics"]["rma_cost"]["value"])
        self.assertEqual(brief["comparison"], "NO_PREVIOUS_SNAPSHOT")
        self.assertEqual(brief["snapshot_deltas"], [])
        self.assertTrue(brief["exceptions"])
        self.assertEqual(brief["exceptions"][-1]["priority"], "P2")

    def test_unverified_numeric_otd_is_not_published_as_a_fact(self):
        briefing = build_daily_brief(summary(days="unknown", reconciled=5))
        self.assertEqual(briefing["metrics"]["shipment_line_otd"]["evidence_state"], "UNKNOWN")
        self.assertIsNone(briefing["metrics"]["shipment_line_otd"]["value"])
        self.assertIn("N/A", render_html(briefing))
        self.assertNotIn("<strong>70.0%</strong>", render_html(briefing))
        self.assertIn("SHIPMENT_DATE_UNVERIFIED",
                      [x["code"] for x in briefing["exceptions"]])

    def test_conflicted_shipment_data_holds_otd_and_next_check(self):
        briefing = build_daily_brief(summary(days="conflicted", reconciled=9))
        self.assertIsNone(briefing["metrics"]["shipment_line_otd"]["value"])
        self.assertEqual(briefing["metrics"]["shipment_line_otd"]["evidence_state"], "CONFLICTED")
        self.assertIn("SHIPMENT_DATE_CONFLICT",
                      [x["code"] for x in briefing["exceptions"]])

    def test_quarantined_rma_is_only_lower_bound_and_no_sensitive_rows(self):
        briefing = build_daily_brief(summary(quarantine=1))
        rma = briefing["metrics"]["rma_observed"]
        self.assertIsNone(rma["value"])
        self.assertEqual(rma["observed_lower_bound"], 2)
        rendered = json.dumps(briefing) + render_html(briefing)
        self.assertIn("at least 2 observed", rendered)
        for forbidden in ("CUSTOMER-123-PRIVATE", "SENSITIVE CUSTOMER DEFECT TEXT",
                          "SHOULD-NEVER-ESCAPE", "JOB-SECRET-77"):
            self.assertNotIn(forbidden, rendered)

    def test_gap_resolution_and_checked_snapshot_delta_without_causality(self):
        earlier = summary(as_of="2026-10-09T14:00:00Z", days="unknown", reconciled=4)
        latest = summary(as_of="2026-10-10T12:00:00Z")
        briefing = build_daily_brief(latest, earlier)
        self.assertIn("SHIPMENT_DATE_UNVERIFIED", briefing["resolved_gap_codes"])
        self.assertNotIn("shipment_line_otd",
                         [row["metric"] for row in briefing["snapshot_deltas"]])
        self.assertEqual(briefing["comparison"], "SAME_PERIOD_DIFFERENT_CUTOFF_SNAPSHOTS")
        self.assertTrue(all("not evidence of cause" in row["interpretation"]
                            for row in briefing["snapshot_deltas"]))

    def test_verified_to_verified_difference_is_described_as_snapshot_only(self):
        old = summary(as_of="2026-10-09T12:00:00Z", rma=1)
        new = summary(as_of="2026-10-10T12:00:00Z", rma=2)
        briefing = build_daily_brief(new, old)
        delta = next(x for x in briefing["snapshot_deltas"] if x["metric"] == "rma_observed")
        self.assertEqual(delta["delta"], 1)
        self.assertIn("snapshot", render_html(briefing).lower())
        self.assertNotIn("new RMA", render_html(briefing))

    def test_unknown_current_never_invents_delta_or_zero(self):
        old = summary(as_of="2026-10-09T12:00:00Z")
        new = summary(as_of="2026-10-10T12:00:00Z", include_ship=False, missing_schedule=1)
        briefing = build_daily_brief(new, old)
        self.assertIsNone(briefing["metrics"]["shipment_lines"]["value"])
        self.assertIsNone(briefing["metrics"]["past_due_open_job_lines"]["value"])
        self.assertNotIn("shipment_lines", [x["metric"] for x in briefing["snapshot_deltas"]])
        self.assertIn("SHIPMENT_EXPORT_MISSING", briefing["new_gap_codes"])

    def test_previous_scope_and_cutoff_must_be_strictly_earlier(self):
        curr = summary()
        same = summary(as_of="2026-10-10T07:00:00-05:00")
        with self.assertRaisesRegex(ValueError, "earlier"):
            build_daily_brief(curr, same)
        newer = summary(as_of="2026-10-11T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "earlier"):
            build_daily_brief(curr, newer)
        other = analyze_site("SITE_B", raw(as_of="2026-10-09T12:00:00Z"))
        with self.assertRaisesRegex(ValueError, "same site"):
            build_daily_brief(curr, other)
        different = summary(as_of="2026-10-09T12:00:00Z")
        different["window_start"] = "2026-09-01"
        with self.assertRaisesRegex(ValueError, "same site"):
            build_daily_brief(curr, different)

    def test_hostile_or_invalid_fields_do_not_enter_output(self):
        current = summary()
        current["gaps"].append({"code": "RAW_UNTRUSTED",
                                "question": "<script>alert(1)</script> PERSONAL DETAILS"})
        brief = build_daily_brief(current)
        s = json.dumps(brief) + render_html(brief)
        self.assertNotIn("RAW_UNTRUSTED", s)
        self.assertNotIn("<script>", s)
        self.assertNotIn("PERSONAL DETAILS", s)
        current = summary()
        current["metrics"]["shipment_line_otd"]["value"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Invalid metric value"):
            build_daily_brief(current)
        current = summary()
        current["site"] = "<img src=x>"
        with self.assertRaisesRegex(ValueError, "Invalid anonymous"):
            build_daily_brief(current)

    def test_reproducible_report_and_no_mutation(self):
        current = summary()
        old = summary(as_of="2026-10-09T12:00:00Z")
        original = json.dumps([current, old], sort_keys=True)
        self.assertEqual(build_daily_brief(current, old), build_daily_brief(current, old))
        self.assertEqual(json.dumps([current, old], sort_keys=True), original)

    def test_cli_real_empty_local_ledger_never_invents_zeros(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "private.sqlite"
            ExportSponge(db).close()
            html = Path(temp) / "morning.html"
            with patch.object(sys, "argv", ["daily_brief", "--database", str(db),
                                            "--site", "SITE_A",
                                            "--start", "2026-10-01",
                                            "--as-of", "2026-10-10T12:00:00Z",
                                            "--out", str(html)]):
                main()
            self.assertTrue(html.is_file())
            brief = json.loads(html.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertIsNone(brief["metrics"]["shipment_line_otd"]["value"])
            self.assertIsNone(brief["metrics"]["rma_observed"]["value"])
            self.assertIn("SHIPMENT_EXPORT_MISSING", [x["code"] for x in brief["exceptions"]])
            self.assertIn("RMA_EXPORT_MISSING", [x["code"] for x in brief["exceptions"]])


if __name__ == "__main__":
    unittest.main()
