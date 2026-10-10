"""Synthetic, identity-free regression for BEAN management intelligence."""
import unittest

from ezbean.jobboss_exports import _count
from ezbean.management_intelligence import analyze_site, compare_sites, render_html


def report(otd=70.0, days="verified", shipped=10, checked=10, dates_missing=0,
           quarantine=0, rma=2, window="2026-09-01", cutoff="2026-10-01T18:00:00Z"):
    return {
        "schema":"BEAN_JOBBOSS_EXPORT_V1",
        "window_start":window,"as_of":cutoff,
        "metrics":{
            "otd_percent_by_shipment_line":otd,
            "shipment_lines":shipped,"on_time_shipment_lines":7,
            "partially_shipped_lines":1,
            "past_due_open_job_lines":None if dates_missing else 2,
            "schedule_due_date_lines":5,
            "schedule_missing_shipped_quantity_lines":dates_missing,
            "rma_entries":rma,"rma_missing_reason_entries":1,
            "rma_quantity":None,"rma_cost_usd":None
        },
        "source_verification":{"shipment_days_early_late":{
            "status":days,"reconciled_lines":checked,
            "unavailable_lines":shipped-checked,"conflicting_lines":1 if days=="conflicted" else 0}},
        "quarantined_rma_rows":[{"row_ref":"SENSITIVE-ORDER-TRAIL-77",
                                 "issue":"private bad date"}]*quarantine,
        "evidence":{"shipment_row_refs":["SENSITIVE-CUSTOMER-ENTITY-55"],
                    "past_due_row_refs":["JOB-SUPER-SECRET"]},
        "rma_reason_counts":{"SECRET_VENDOR_REASON":2}
    }


class ManagementIntelligenceTests(unittest.TestCase):
    def test_normalizes_thousands_without_accepting_corrupt_number(self):
        self.assertEqual(_count("1,250","QtyOrdered"),1250)
        self.assertEqual(_count("4,000.00","QtyOrdered"),4000)
        self.assertEqual(_count("0","QtyShipped"),0)
        for s in ("1,2","2,23,000","2.5","-1","1e4","NaN"):
            with self.subTest(s=s):
                with self.assertRaises(ValueError):_count(s,"QtyOrdered")

    def test_verified_only_when_source_day_column_reconciles(self):
        a=analyze_site("SITE_A",report())
        self.assertEqual(a["metrics"]["shipment_line_otd"]["state"],"VERIFIED")
        b=analyze_site("SITE_A",report(days="unknown",checked=5))
        self.assertEqual(b["metrics"]["shipment_line_otd"]["state"],"UNKNOWN")
        c=analyze_site("SITE_A",report(days="conflicted",checked=9))
        self.assertEqual(c["metrics"]["shipment_line_otd"]["state"],"CONFLICTED")
        self.assertIn("SHIPMENT_DATE_CONFLICT",{x["code"] for x in c["gaps"]})

    def test_blank_shipping_is_unknown_not_open_zero(self):
        x=analyze_site("SITE_A",report(dates_missing=12))
        self.assertIsNone(x["metrics"]["past_due_open_job_lines"]["value"])
        self.assertEqual(x["metrics"]["past_due_open_job_lines"]["state"],"UNKNOWN")
        self.assertIn("SCHEDULE_SHIP_STATUS_UNKNOWN",{g["code"] for g in x["gaps"]})

    def test_quarantine_preserves_lower_bound_and_missing_reason(self):
        x=analyze_site("SITE_A",report(quarantine=1))
        self.assertEqual(x["metrics"]["rma_observed"]["value"],2)
        self.assertEqual(x["metrics"]["rma_observed"]["state"],"UNKNOWN")
        codes={g["code"] for g in x["gaps"]}
        self.assertIn("RMA_DATE_QUARANTINE",codes)
        self.assertIn("RMA_REASON_MISSING",codes)

    def test_unknown_peer_makes_no_comparison_claim(self):
        a=analyze_site("SITE_A",report())
        x=compare_sites(a)
        self.assertIsNone(x["comparison"]["ranking"])
        self.assertIsNone(x["comparison"]["difference_points"])
        self.assertEqual(x["comparison"]["state"],"UNKNOWN")
        self.assertIn("PEER_COMPARISON_NOT_VERIFIED",{g["code"] for g in x["gaps"]})

    def test_matching_verified_sites_compare_same_metric(self):
        a=analyze_site("SITE_A",report(otd=70.0))
        b=analyze_site("SITE_B",report(otd=60.0))
        z=compare_sites(a,b)
        self.assertEqual(z["comparison"]["difference_points"],10.0)
        self.assertEqual(z["comparison"]["ranking"],"primary_higher")
        self.assertEqual(z["comparison"]["state"],"VERIFIED")
        self.assertNotIn("PEER_COMPARISON_NOT_VERIFIED",{g["code"] for g in z["gaps"]})

    def test_missing_peer_verification_prevents_ranking(self):
        a=analyze_site("SITE_A",report())
        b=analyze_site("SITE_B",report(otd=20.0,days="unknown",checked=0))
        z=compare_sites(a,b)
        self.assertEqual(z["comparison"]["state"],"UNKNOWN")
        self.assertIsNone(z["comparison"]["difference_points"])

    def test_different_windows_prevent_ranking(self):
        a=analyze_site("SITE_A",report())
        b=analyze_site("SITE_B",report(cutoff="2026-10-02T18:00:00Z"))
        z=compare_sites(a,b)
        self.assertEqual(z["comparison"]["state"],"UNKNOWN")

    def test_corrected_state_requires_old_gap_and_new_evidence(self):
        before=analyze_site("SITE_A",report(days="unknown",checked=0))
        after=analyze_site("SITE_A",report(days="verified",checked=10))
        x=compare_sites(after,previous=before)
        self.assertIn("SHIPMENT_DATE_UNVERIFIED",x["resolved_gaps"])
        self.assertIn("shipment_line_otd",x["corrected_metrics"])
        self.assertEqual(after["metrics"]["shipment_line_otd"]["state"],"CORRECTED")

    def test_previous_different_window_rejected(self):
        a=analyze_site("SITE_A",report())
        old=analyze_site("SITE_A",report(window="2026-08-01"))
        with self.assertRaises(ValueError):compare_sites(a,previous=old)

    def test_anonymous_html_escapes_note_and_never_exposes_source(self):
        a=analyze_site("SITE_A",report(quarantine=1))
        text=render_html(compare_sites(a),"<script>nope</script>")
        self.assertNotIn("<script>","".join(text.splitlines()))
        self.assertIn("&lt;script&gt;",text)
        self.assertNotIn("SENSITIVE-CUSTOMER-ENTITY-55",text)
        self.assertNotIn("SENSITIVE-ORDER-TRAIL-77",text)
        self.assertNotIn("JOB-SUPER-SECRET",text)
        self.assertNotIn("SECRET_VENDOR_REASON",text)
        self.assertIn("BEAN | Executive Evidence Report",text)

    def test_identity_strings_never_leave_site_summary(self):
        a=analyze_site("SITE_A",report(quarantine=1))
        import json
        serialized=json.dumps(a)
        for sentinel in ("SENSITIVE-CUSTOMER-ENTITY-55","SENSITIVE-ORDER-TRAIL-77",
                         "JOB-SUPER-SECRET","SECRET_VENDOR_REASON"):
            self.assertNotIn(sentinel,serialized)

if __name__=="__main__":
    unittest.main()
