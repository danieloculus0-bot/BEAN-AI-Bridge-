"""Adversarial tests for historical weather foresight/leakage and score isolation."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date, timedelta

from experiments.weather_chatfield_lab import weather_lab as w


class CausalityTests(unittest.TestCase):
    def test_issuance_windows_are_fixed_and_matured(self):
        dates = list(w.issuance_days())
        self.assertGreaterEqual(len(dates), 11)
        self.assertEqual(len(dates), len(set(dates)))
        for d in dates:
            self.assertGreater(d, w.START)
            self.assertLessEqual(d + timedelta(days=30), w.OBS_END)

    def test_late_truth_cannot_change_prior_trust(self):
        issue = date(2026, 7, 21)
        cases = [
            {"last_valid": "2026-07-14"},  # 7d old, mature
            {"last_valid": "2026-07-16"},  # 5d old, unpublishable
            {"last_valid": "2026-07-21"},  # same day, inaccessible
            {"last_valid": "2026-08-09"},  # in the future, inaccessible
        ]
        self.assertEqual(w.eligible(cases, issue), cases[:1])

    def test_30_day_is_true_asof_climatology_never_future_history(self):
        original = {}
        for yr in range(2015, 2025):
            for delta in range(-8, 9):
                day = date(yr, 6, 15) + timedelta(days=delta)
                original[day.isoformat()] = dict(
                    temperature_2m_max=20.0, temperature_2m_min=9.0, precipitation_sum=1.0)
        a = w.history_baseline(original, date(2026, 6, 15))
        self.assertEqual(a["temperature_2m_max"], 20.0)
        original["2026-06-15"] = dict(
            temperature_2m_max=9999, temperature_2m_min=9999, precipitation_sum=9999)
        self.assertEqual(w.history_baseline(original, date(2026, 6, 15)), a)

    def test_forecast_append_requires_all_valid_dates(self):
        issue = date(2026, 6, 15)
        stub = {str(issue + timedelta(days=n)): dict(
            temperature_2m_max=19, temperature_2m_min=7, precipitation_sum=0)
            for n in range(1, 7)}
        output = []
        self.assertFalse(w.add_predictions(output, issue, 7, "ECMWF_IFS_HRES",
                                           stub, "ECMWF_IFS_HRES", "a" * 64))
        self.assertEqual(output, [])

    def test_grade_rejects_future_issued_forecast_date(self):
        issued = date(2026, 6, 15)
        fake = dict(schema="bean_weather_1", observations_embedded=False,
                    issue_dates=[issued.isoformat()], unavailable=[],
                    forecast_decisions=[
                        {"issue": issued.isoformat(),
                         "valid_date": "2026-06-15", "horizon": 7,
                         "source": "ECMWF_IFS_HRES",
                         "provider_family": "ECMWF_IFS_HRES",
                         "source_sha256": "a" * 64,
                         "training_cutoff_exclusive": "2025-10-11",
                         "values": {"temperature_2m_max": 19.0,
                                    "temperature_2m_min": 10.0,
                                    "precipitation_sum": 1.0}}
                    ])
        actual = dict(reference_type="ERA5_GRIDDED_REANALYSIS_NOT_STATION_OBSERVATION",
                      observations={})
        with tempfile.TemporaryDirectory() as t:
            a, b, c = [str(Path(t)/n) for n in ("pred.json", "actual.json", "output.json")]
            w.write_json(a, fake)
            w.write_json(b, actual)
            with self.assertRaisesRegex(ValueError, "Invalid forecast issuance"):
                w.run_grade(a, b, c)

    def test_unavailable_never_counts_as_model_win(self):
        fake = dict(schema="bean_weather_1", observations_embedded=False,
                    issue_dates=["2026-06-15"],
                    unavailable=[{"source":"ARCHIVED_30D_MODEL","horizon":30,
                                  "reason":"not provided"}],
                    forecast_decisions=[])
        actual = dict(reference_type="ERA5_GRIDDED_REANALYSIS_NOT_STATION_OBSERVATION",
                      observations={})
        with tempfile.TemporaryDirectory() as t:
            a, b, c = [str(Path(t)/n) for n in ("pred.json", "actual.json", "output.json")]
            w.write_json(a, fake)
            w.write_json(b, actual)
            with self.assertRaisesRegex(RuntimeError, "No independently scored"):
                w.run_grade(a, b, c)


if __name__ == "__main__":
    unittest.main()
