import json
import tempfile
import unittest
from pathlib import Path

from ezbean import Observation, Ledger, calculate, FixtureAdapter, run_cycle

FIXTURE = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic_erp.jsonl'
AS_OF = '2026-10-08T16:00:00+00:00'
START = '2026-10-01'


class EZBeanBridgeTests(unittest.TestCase):
    def load(self):
        return list(FixtureAdapter(FIXTURE).read_observations())

    def test_expected_synthetic_kpis(self):
        result = calculate(self.load(), START, AS_OF).kpis
        self.assertEqual(result['otd_percent'].value, '50.00')
        self.assertEqual(result['shipments_completed'].value, '2')
        self.assertEqual(result['past_due_open_jobs'].value, '1')
        self.assertEqual(result['rma_count'].value, '2')
        self.assertEqual(result['rma_quantity'].value, '3')
        self.assertEqual(result['rma_cost'].value, '200.00')
        self.assertEqual(result['good_units'].value, '90')
        self.assertEqual(result['scrap_units'].value, '10')
        self.assertEqual(result['scrap_percent'].value, '10.00')

    def test_replay_is_stable_regardless_of_input_order(self):
        original = self.load()
        baseline = calculate(original, START, AS_OF).to_dict()
        self.assertEqual(calculate(list(reversed(original)), START, AS_OF).to_dict(), baseline)

    def test_duplicate_event_is_idempotent(self):
        with tempfile.TemporaryDirectory() as work:
            ledger = Ledger(Path(work) / 'ledger.db')
            report, findings, added = run_cycle(FixtureAdapter(FIXTURE), ledger, START, AS_OF)
            self.assertEqual(added, 7)
            self.assertEqual(len(findings), 2)
            second, second_findings, second_added = run_cycle(FixtureAdapter(FIXTURE), ledger, START, AS_OF)
            self.assertEqual(second_added, 0)
            self.assertEqual(second.to_dict(), report.to_dict())
            self.assertEqual(second_findings, findings)
            ledger.close()
            restored = Ledger(Path(work) / 'ledger.db')
            self.assertEqual(calculate(restored.replay(), START, AS_OF).to_dict(), report.to_dict())
            restored.close()

    def test_conflicting_event_identity_is_rejected(self):
        ledger = Ledger()
        first = self.load()[0]
        self.assertTrue(ledger.ingest(first))
        conflicting = Observation(first.source, first.event_id, first.entity_type,
                                  first.entity_id, first.observed_at, {'due_date': '2026-09-01'})
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            ledger.ingest(conflicting)
        ledger.close()

    def test_correction_replays_as_of_old_or_new(self):
        initial = self.load()
        correction = Observation.from_dict({
            'source': 'synthetic_erp', 'event_id': 'job-002-v2',
            'entity_type': 'job', 'entity_id': 'J002',
            'observed_at': '2026-10-09T09:00:00+00:00',
            'payload': {'due_date': '2026-10-05', 'shipped_date': '2026-10-05'},
        })
        before = calculate(initial + [correction], START, AS_OF)
        after = calculate(initial + [correction], START, '2026-10-09T16:00:00+00:00')
        self.assertEqual(before.kpis['otd_percent'].value, '50.00')
        self.assertEqual(after.kpis['otd_percent'].value, '100.00')
        self.assertIn('synthetic_erp:job-002-v2', after.kpis['otd_percent'].evidence_ids)

    def test_absent_shipments_returns_unknown_not_zero(self):
        subset = [o for o in self.load() if o.entity_type == 'rma']
        result = calculate(subset, START, AS_OF)
        self.assertIsNone(result.kpis['otd_percent'].value)
        self.assertIsNone(result.kpis['scrap_percent'].value)

    def test_invalid_quantities_fail_closed(self):
        original = self.load()
        bad = Observation('synthetic_erp', 'bad', 'rma', 'bad', AS_OF,
                          {'opened_date': '2026-10-08', 'quantity': -4, 'cost': '0.00'})
        with self.assertRaisesRegex(ValueError, 'nonnegative'):
            calculate(original + [bad], START, AS_OF)

    def test_asof_report_ignores_later_events(self):
        base = self.load()
        future = Observation('synthetic_erp', 'future-rma', 'rma', 'R999',
                             '2026-10-10T10:00:00+00:00',
                             {'opened_date': '2026-10-10', 'quantity': 4, 'cost': '50'})
        self.assertEqual(calculate(base, START, AS_OF).to_dict(),
                         calculate(base + [future], START, AS_OF).to_dict())

    def test_future_shipment_does_not_hide_overdue_job(self):
        future_ship = Observation('synthetic_erp', 'future-job', 'job', 'J999', AS_OF,
                                  {'due_date': '2026-10-02', 'shipped_date': '2026-10-10'})
        report = calculate([future_ship], START, AS_OF)
        self.assertEqual(report.kpis['past_due_open_jobs'].value, '1')
        self.assertEqual(report.kpis['shipments_completed'].value, '0')

    def test_no_root_cause_is_invented(self):
        ledger = Ledger()
        _, findings, _ = run_cycle(FixtureAdapter(FIXTURE), ledger, START, AS_OF)
        self.assertEqual({f.classification for f in findings}, {'rule_observation'})
        self.assertTrue(all(f.evidence_ids for f in findings))
        ledger.close()


if __name__ == '__main__':
    unittest.main()
