"""Independent invariant-hunter contracts; never require an existing defect.

The lab must keep passing when BEAN successfully repairs a discovered defect.
Synthetic injected violations prove that the discovery mechanism itself works.
"""
from datetime import datetime, timedelta, timezone
import copy
import unittest
from unittest.mock import patch

from tools import bean_metamorphic_hunter as hunter


class MetamorphicHunterTests(unittest.TestCase):
    def test_fixtures_are_generic_synthetic_and_claim_scoped_coverage(self):
        date = datetime(2026, 10, 10, 0, 30, tzinfo=timezone.utc)
        for domain in hunter.DOMAINS:
            start, rows = hunter.build_fixture(domain, date)
            self.assertEqual(len(rows), 2)
            self.assertEqual(start, "2026-10-01")
            self.assertEqual(rows[0].entity_type, domain)
            self.assertEqual(rows[0].source, "synthetic_meta_erp")
            self.assertEqual(rows[1].payload["domain"], domain)
            self.assertTrue(rows[1].payload["complete"])

    def test_equivalent_timestamps_mean_exactly_same_instant(self):
        dt = datetime(2026, 10, 10, 0, 30, tzinfo=timezone.utc)
        for hours in hunter.OFFSETS:
            counterpart = dt.astimezone(timezone(timedelta(hours=hours)))
            self.assertEqual(counterpart, dt)
            self.assertEqual(counterpart.astimezone(timezone.utc), dt)

    def test_different_results_are_detected_without_knowledge_of_specific_bug(self):
        class FakeReport:
            def __init__(self, observed):
                self.observed = observed
            def to_dict(self):
                return {
                    "input_count": 2,
                    "source_coverage": {"rma": {"state": "ASSERTED_COMPLETE"}},
                    "kpis": {"rma_count": {"value": str(self.observed), "evidence_ids": []}},
                    "as_of": "caller lexical representation ignored",
                }

        def intentionally_wrong(rows, start, as_of):
            return FakeReport(0 if as_of.endswith("-05:00") else 1)

        row = hunter.obs("rma", "synthetic", "2026-10-10T00:00:00Z",
                         {"opened_date":"2026-10-10","quantity":1,"cost":"1.00"})
        result = hunter.compare_one([row], "2026-10-01",
                                    "2026-10-10T00:30:00+00:00",
                                    "2026-10-09T19:30:00-05:00",
                                    calculator=intentionally_wrong)
        self.assertFalse(result["equal"])
        self.assertEqual(result["changed_kpis"], ["rma_count"])
        self.assertEqual(result["changed_coverage"], [])
        self.assertEqual(result["baseline"]["kpis"]["rma_count"]["value"], "1")
        self.assertEqual(result["alternate"]["kpis"]["rma_count"]["value"], "0")

    def test_projection_excludes_textual_cutoff_not_evidence(self):
        class FakeReport:
            def __init__(self, at):
                self.at = at
            def to_dict(self):
                return {"as_of": self.at, "input_count":1, "source_coverage":{},
                        "kpis":{"test":{"value":1, "evidence_ids":["synthetic:fact"]}}}
        self.assertEqual(hunter.projection(FakeReport("UTC")),
                         hunter.projection(FakeReport("other-offset")))
        b = hunter.projection(FakeReport("UTC"))
        other = copy.deepcopy(b)
        other["kpis"]["test"]["value"] = 0
        self.assertNotEqual(other, b)

    def test_seed_is_replayable_without_web_or_customer_data(self):
        first = hunter.run(seed=2001, trials=15)
        second = hunter.run(seed=2001, trials=15)
        self.assertEqual(first, second)
        self.assertEqual(first["invariant_checks"], 45)
        self.assertEqual(first["schema"], hunter.SCHEMA)
        self.assertEqual(first["receipt_sha256"], hunter.digest({
            key: value for key, value in first.items() if key != "receipt_sha256"
        }))
        for finding in first["findings"]:
            self.assertEqual(finding["synthetic_rows"][0]["source"], "synthetic_meta_erp")

    def test_a_different_seed_changes_the_synthetic_experiment(self):
        self.assertNotEqual(hunter.run(seed=2001, trials=12)["receipt_sha256"],
                            hunter.run(seed=2002, trials=12)["receipt_sha256"])

    def test_invariant_results_survive_original_fix_without_false_failure(self):
        # This test intentionally makes NO claim about whether the live code
        # currently violates a property. Both a finding and a clean run count.
        result = hunter.run(seed=1, trials=3)
        self.assertIn(result["status"],
                      ("FINDINGS_REQUIRE_PEER_REVIEW", "NO_VIOLATION_OBSERVED"))
        self.assertGreaterEqual(result["finding_occurrences"], 0)
        self.assertEqual(result["synthetic_only"], True)

    def test_trial_budget_is_bounded(self):
        for invalid in (0, -1, 2001):
            with self.assertRaises(ValueError):
                hunter.run(seed=1, trials=invalid)


if __name__ == "__main__":
    unittest.main()
