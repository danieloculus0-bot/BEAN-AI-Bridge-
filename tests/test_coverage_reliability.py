"""Coverage and import atomicity: avoid converting unknown to false certainty."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ezbean import Ledger, Observation, calculate
from ezbean.bridge import RuleThinkingModule

START = '2026-10-01'
AS_OF = '2026-10-08T16:00:00+00:00'


def obs(kind, event_id, payload, *, source='report_A', observed_at=AS_OF):
    return Observation(source, event_id, kind, event_id, observed_at, payload)


def declared(domain, *, source='report_A', event_id=None, through=AS_OF,
             complete=True, scope=None):
    return obs('source_coverage', event_id or ('cover-' + domain), {
        'domain': domain, 'window_start': START, 'through': through,
        'scope': scope or ('full_snapshot' if domain == 'job' else 'reporting_window'),
        'complete': complete,
    }, source=source)


class CoverageReliabilityTests(unittest.TestCase):
    def test_no_records_means_unknown_in_all_categories(self):
        report = calculate([], START, AS_OF)
        for key in ('shipments_completed', 'past_due_open_jobs', 'rma_count',
                    'rma_quantity', 'rma_cost', 'good_units', 'scrap_units',
                    'otd_percent', 'scrap_percent'):
            self.assertIsNone(report.kpis[key].value, key)
        self.assertTrue(all(v['state'] == 'UNKNOWN' for v in report.coverage.values()))
        findings = RuleThinkingModule().analyze(report)
        self.assertTrue(any('N/A' in f.statement for f in findings))

    def test_independent_source_assertions_allow_explicit_zero(self):
        events = [declared(kind) for kind in ('job', 'rma', 'production')]
        report = calculate(events, START, AS_OF)
        self.assertEqual(report.kpis['shipments_completed'].value, '0')
        self.assertEqual(report.kpis['past_due_open_jobs'].value, '0')
        self.assertEqual(report.kpis['rma_count'].value, '0')
        self.assertEqual(report.kpis['rma_quantity'].value, '0')
        self.assertEqual(report.kpis['rma_cost'].value, '0.00')
        self.assertEqual(report.kpis['good_units'].value, '0')
        self.assertEqual(report.kpis['scrap_units'].value, '0')
        self.assertIsNone(report.kpis['otd_percent'].value)  # zero denominator
        self.assertIsNone(report.kpis['scrap_percent'].value)  # zero denominator
        self.assertEqual(report.coverage['rma']['state'], 'ASSERTED_COMPLETE')
        self.assertIn('report_A:cover-rma', report.kpis['rma_count'].evidence_ids)
        self.assertIn('not independently authenticated', report.kpis['rma_count'].note)
        self.assertEqual(report.to_dict()['schema_version'], '0.2')

    def test_partial_observations_are_not_complete_source_coverage(self):
        samples = [
            obs('job', 'J1', {'due_date': '2026-10-05', 'shipped_date': '2026-10-05'}),
            obs('rma', 'R1', {'opened_date': '2026-10-07', 'quantity': 0, 'cost': '0'}),
        ]
        report = calculate(samples, START, AS_OF)
        self.assertEqual(report.kpis['shipments_completed'].value, '1')
        self.assertEqual(report.kpis['rma_count'].value, '1')
        self.assertEqual(report.kpis['rma_quantity'].value, '0')
        self.assertIsNone(report.kpis['past_due_open_jobs'].value)
        self.assertIsNone(report.kpis['good_units'].value)
        self.assertEqual(report.coverage['job']['state'], 'UNKNOWN')
        self.assertIn('Observed evidence only', report.kpis['shipments_completed'].note)

    def test_incomplete_stale_or_wrong_scope_never_certifies_zero(self):
        variants = [
            declared('rma', complete=False),
            declared('rma', through='2026-10-07T16:00:00+00:00'),
            declared('rma', scope='full_snapshot'),
        ]
        for record in variants:
            with self.subTest(record=record.event_id, payload=record.payload):
                result = calculate([record], START, AS_OF)
                self.assertIsNone(result.kpis['rma_count'].value)

    def test_all_observed_sources_need_matching_assertion(self):
        samples = [
            obs('job', 'J1', {'due_date': '2026-10-05', 'shipped_date': None},
                source='report_B'),
            declared('job', source='report_A'),
        ]
        report = calculate(samples, START, AS_OF)
        self.assertEqual(report.kpis['past_due_open_jobs'].value, '1')
        self.assertIsNone(report.kpis['shipments_completed'].value)
        self.assertEqual(report.coverage['job']['state'], 'UNKNOWN')

    def test_later_revocation_overrides_earlier_complete_claim(self):
        old = obs('source_coverage', 'old-complete', {
            'domain': 'rma', 'window_start': START, 'through': AS_OF,
            'complete': True, 'scope': 'reporting_window',
        }, observed_at='2026-10-08T12:00:00+00:00')
        revoked = obs('source_coverage', 'zz-new-revocation', {
            'domain': 'rma', 'window_start': START, 'through': AS_OF,
            'complete': False, 'scope': 'reporting_window',
        }, observed_at='2026-10-08T15:00:00+00:00')
        for events in ([old, revoked], [revoked, old]):
            result = calculate(events, START, AS_OF)
            self.assertIsNone(result.kpis['rma_count'].value)
            self.assertEqual(result.coverage['rma']['state'], 'UNKNOWN')

    def test_later_malformed_coverage_revokes_older_assertion(self):
        valid = declared('production')
        old = Observation(valid.source, 'old-coverage', 'source_coverage',
                          'coverage-one', '2026-10-08T12:00:00+00:00', valid.payload)
        invalid = Observation(valid.source, 'new-bad-coverage', 'source_coverage',
                              'coverage-two', '2026-10-08T15:00:00+00:00', {
                                  'domain': 'production', 'scope': 'reporting_window',
                                  'complete': True, 'window_start': START,
                                  'through': None,
                              })
        result = calculate([old, invalid], START, AS_OF)
        self.assertIsNone(result.kpis['scrap_units'].value)
        self.assertEqual(result.coverage['production']['state'], 'UNKNOWN')

    def test_newer_valid_renewal_restores_zero_with_new_evidence(self):
        revoked = Observation('report_A', 'old-revocation', 'source_coverage',
                              'old-state', '2026-10-08T12:00:00+00:00', {
                                  'domain': 'rma', 'scope': 'reporting_window',
                                  'window_start': START, 'through': AS_OF,
                                  'complete': False})
        renewed = Observation('report_A', 'fresh-coverage', 'source_coverage',
                              'new-state', '2026-10-08T15:00:00+00:00', {
                                  'domain': 'rma', 'scope': 'reporting_window',
                                  'window_start': START, 'through': AS_OF,
                                  'complete': True})
        result = calculate([renewed, revoked], START, AS_OF)
        self.assertEqual(result.kpis['rma_count'].value, '0')
        self.assertEqual(result.kpis['rma_count'].evidence_ids,
                         ('report_A:fresh-coverage',))

    def test_future_completeness_event_does_not_certify_historical_report(self):
        later = obs('source_coverage', 'future-cover', {
            'domain': 'rma', 'window_start': START, 'through': AS_OF,
            'complete': True, 'scope': 'reporting_window',
        }, observed_at='2026-10-09T10:00:00+00:00')
        self.assertIsNone(calculate([later], START, AS_OF).kpis['rma_count'].value)

    def test_conflicting_batch_rolls_back_every_new_row_and_preserves_old(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'events.sqlite'
            ledger = Ledger(path)
            original = obs('job', 'stable', {'due_date': '2026-10-05'})
            self.assertTrue(ledger.ingest(original))
            newly = obs('rma', 'new', {'opened_date': '2026-10-08'})
            collision = obs('job', 'stable', {'due_date': '2026-10-02'})
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                ledger.ingest_all(iter((newly, collision)))
            self.assertEqual(ledger.replay(), [original])
            ledger.close()
            reopened = Ledger(path)
            self.assertEqual(reopened.replay(), [original])
            self.assertEqual(reopened.ingest_all([newly, newly]), 1)
            self.assertEqual(reopened.ingest_all([newly]), 0)
            reopened.close()

    def test_stream_parse_error_rolls_back_inserted_prefix(self):
        ledger = Ledger()
        first = obs('job', 'prefix', {'due_date': '2026-10-05'})
        def failing_stream():
            yield first
            raise ValueError('synthetic invalid row 2')
        with self.assertRaisesRegex(ValueError, 'invalid row'):
            ledger.ingest_all(failing_stream())
        self.assertEqual(ledger.replay(), [])
        ledger.close()

    def test_unserializable_late_event_rolls_back_prefix(self):
        ledger = Ledger()
        first = obs('job', 'prefix', {'due_date': '2026-10-05'})
        invalid = obs('job', 'invalid', {'due_date': object()})
        with self.assertRaises(TypeError):
            ledger.ingest_all([first, invalid])
        self.assertEqual(ledger.replay(), [])
        ledger.close()


if __name__ == '__main__':
    unittest.main()
