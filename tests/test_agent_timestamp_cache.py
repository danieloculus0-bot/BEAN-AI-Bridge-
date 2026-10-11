"""Behavioral equivalence plus an objective, deterministic parse-count metric."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import ezbean.core as core
from ezbean.core import Observation


class TimestampCacheRegression(unittest.TestCase):
    def test_timestamp_parse_once_per_input_and_latest_wins(self):
        events = [
            Observation("erp", str(i), "job", "J1",
                        f"2026-10-01T00:00:{i:02d}+00:00", {})
            for i in range(8)
        ]
        with patch.object(core, "utc_datetime", wraps=core.utc_datetime) as wrapped:
            rows = core.latest_entities(
                list(reversed(events)), datetime(2026, 10, 10, tzinfo=timezone.utc))
            self.assertEqual(wrapped.call_count, len(events))
        self.assertEqual(rows[("erp", "job", "J1")].event_id, "7")

    def test_future_events_are_ignored(self):
        events = [
            Observation("erp", "old", "job", "J1", "2026-10-01T00:00:00Z", {}),
            Observation("erp", "new", "job", "J1", "2026-11-01T00:00:00Z", {}),
        ]
        rows = core.latest_entities(
            events, datetime(2026, 10, 10, tzinfo=timezone.utc))
        self.assertEqual(rows[("erp", "job", "J1")].event_id, "old")
