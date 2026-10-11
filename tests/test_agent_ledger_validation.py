"""Regression against malformed direct Observation instances."""
import unittest

from ezbean.core import Observation
from ezbean.store import Ledger


class DurableLedgerIngressRegression(unittest.TestCase):
    def test_direct_invalid_timestamp_must_fail_before_storage(self):
        ledger = Ledger()
        entry = Observation("erp", "event", "job", "J1", "bad-timestamp",
                            {"due_date": "2026-10-01"})
        with self.assertRaises(ValueError):
            ledger.ingest(entry)
        self.assertEqual(ledger.replay(), [])
        ledger.close()

    def test_direct_blank_identity_must_fail_before_storage(self):
        ledger = Ledger()
        entry = Observation("", "event", "job", "J1",
                            "2026-10-10T00:00:00Z", {})
        with self.assertRaises(ValueError):
            ledger.ingest(entry)
        self.assertEqual(ledger.replay(), [])
        ledger.close()

    def test_direct_bad_payload_rolls_back_full_batch(self):
        ledger = Ledger()
        first = Observation("erp", "valid", "job", "J1",
                            "2026-10-10T00:00:00Z", {"due_date": "2026-10-01"})
        bad = Observation("erp", "invalid", "job", "J2",
                          "2026-10-10T00:00:00Z", ["not", "a", "dict"])
        with self.assertRaises(ValueError):
            ledger.ingest_all([first, bad])
        self.assertEqual(ledger.replay(), [])
        ledger.close()

    def test_valid_observation_still_ingests_and_is_idempotent(self):
        ledger = Ledger()
        entry = Observation("erp", "valid", "job", "J1",
                            "2026-10-10T00:00:00Z", {"due_date": "2026-10-01"})
        self.assertTrue(ledger.ingest(entry))
        self.assertFalse(ledger.ingest(entry))
        self.assertEqual(len(ledger.replay()), 1)
        ledger.close()
