"""Blind peer challenge: one business instant, two equivalent timestamp spellings.

This file intentionally fails on the pinned production baseline. It is a
challenge fixture, NOT a proposed production fix. Do not merge it alone.
All events are fictional. Test hypotheses by changing the production
implementation on a separate candidate branch, never by editing this oracle.
"""
from __future__ import annotations

import unittest

from ezbean import Observation, calculate

UTC_CUTOFF = "2026-10-10T00:30:00+00:00"
SAME_INSTANT_IN_CENTRAL = "2026-10-09T19:30:00-05:00"
WINDOW_START = "2026-10-01"


def event(kind, ident, at, payload):
    return Observation(
        source="synthetic_utc_erp",
        event_id=ident,
        entity_type=kind,
        entity_id=ident,
        observed_at=at,
        payload=payload,
    )


def source_snapshot(domain):
    return event(
        "source_coverage", "coverage_" + domain,
        "2026-10-10T00:25:00Z",
        {
            "domain": domain,
            "window_start": WINDOW_START,
            "through": UTC_CUTOFF,
            "scope": "full_snapshot" if domain == "job" else "reporting_window",
            "complete": True,
        },
    )


class MidnightParityPeerChallenge(unittest.TestCase):
    def test_same_instant_never_changes_observed_rma_into_asserted_zero(self):
        records = [
            event(
                "rma", "R_001", "2026-10-10T00:20:00Z",
                {"opened_date": "2026-10-10", "quantity": 1, "cost": "37.50"},
            ),
            source_snapshot("rma"),
        ]
        in_utc = calculate(records, WINDOW_START, UTC_CUTOFF)
        in_central = calculate(records, WINDOW_START, SAME_INSTANT_IN_CENTRAL)
        self.assertEqual(in_utc.coverage["rma"]["state"], "ASSERTED_COMPLETE")
        self.assertEqual(in_central.coverage["rma"]["state"], "ASSERTED_COMPLETE")
        self.assertEqual(in_utc.kpis["rma_count"].value, "1")
        self.assertEqual(
            in_central.kpis["rma_count"].value,
            in_utc.kpis["rma_count"].value,
            "Same instant unexpectedly changed an observed RMA to zero",
        )
        self.assertEqual(
            in_central.kpis["rma_cost"].value,
            in_utc.kpis["rma_cost"].value,
        )

    def test_same_instant_does_not_change_eligibility_of_window_start(self):
        # Both encodings identify exactly the same point in time.
        first = calculate([], "2026-10-10", UTC_CUTOFF)
        second = calculate([], "2026-10-10", SAME_INSTANT_IN_CENTRAL)
        self.assertEqual(first.kpis["rma_count"].value, second.kpis["rma_count"].value)

    def test_same_instant_keeps_job_and_production_date_windows_stable(self):
        records = [
            event(
                "job", "J_001", "2026-10-10T00:15:00Z",
                {"due_date": "2026-10-09", "shipped_date": "2026-10-10"},
            ),
            event(
                "production", "P_001", "2026-10-10T00:15:00Z",
                {"production_date": "2026-10-10", "good_units": 90, "scrap_units": 10},
            ),
            source_snapshot("job"),
            source_snapshot("production"),
        ]
        first = calculate(records, WINDOW_START, UTC_CUTOFF)
        second = calculate(records, WINDOW_START, SAME_INSTANT_IN_CENTRAL)
        for metric in ("shipments_completed", "otd_percent", "past_due_open_jobs",
                       "good_units", "scrap_units", "scrap_percent"):
            with self.subTest(metric=metric):
                self.assertEqual(
                    first.kpis[metric].value, second.kpis[metric].value,
                    "Equivalent cutoff instants produced different KPI values",
                )

    def test_absolute_instant_filtering_remains_correct(self):
        records = [
            event(
                "rma", "R_before", "2026-10-10T00:20:00Z",
                {"opened_date": "2026-10-10", "quantity": 1, "cost": "1.00"},
            ),
            event(
                "rma", "R_after", "2026-10-10T00:31:00Z",
                {"opened_date": "2026-10-10", "quantity": 1, "cost": "999.00"},
            ),
            source_snapshot("rma"),
        ]
        a = calculate(records, WINDOW_START, UTC_CUTOFF)
        b = calculate(records, WINDOW_START, SAME_INSTANT_IN_CENTRAL)
        self.assertEqual(a.kpis["rma_count"].value, "1")
        self.assertNotIn("synthetic_utc_erp:R_after", a.kpis["rma_count"].evidence_ids)
        self.assertEqual(a.kpis["rma_count"].value, b.kpis["rma_count"].value)


if __name__ == "__main__":
    unittest.main()
