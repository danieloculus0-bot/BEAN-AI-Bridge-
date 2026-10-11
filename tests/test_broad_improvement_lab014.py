"""Lab014 tests: recovery, stochastic audit bounds and crash-safe continuity."""
import copy
import json
import unittest

from experiments.broad_improvement.lab012 import Policy
from experiments.broad_improvement.lab014 import (
    FROZEN_CONTROLS, RecoveryControls, RecoveryLearner, episodes,
    paired_advantage, replay,
)


def observations():
    return [{"id": str(i), "features": {
        "surprise": 1.0 if i < 3 else .02,
        "contradiction": 1.0 if 3 <= i < 6 else .02,
        "coverage_gap": .02, "echo_risk": .02,
    }} for i in range(12)]


def sample(observations_, first: bool):
    return [{"id": "0", "truth": first}, {"id": "3", "truth": not first}]


class RecoveryLabTests(unittest.TestCase):
    def make(self):
        choices = {"broad": Policy((8, 0, 0, 0)),
                   "alternative": Policy((0, 8, 0, 0))}
        controls = RecoveryControls(recent_worlds=8, confirmation=2,
                                    standard_error_multiplier=.5,
                                    minimum_lift=.5, cooldown=0)
        return RecoveryLearner(choices, controls)

    def test_paired_estimator_symmetric_and_evidence_only(self):
        a = {"selections": {"broad": ["a"], "alternative": ["b"]},
             "sample_probability": .5,
             "audits": [{"id": "a", "truth": False}, {"id": "b", "truth": True}]}
        forward = paired_advantage([a, a], "alternative", "broad")
        backward = paired_advantage([a, a], "broad", "alternative")
        self.assertAlmostEqual(forward["mean_advantage"], 16.0)
        self.assertAlmostEqual(backward["mean_advantage"], -16.0)
        self.assertEqual(forward["standard_error"], 0.0)

    def test_wrong_strategy_can_be_revised_then_restored(self):
        x = self.make()
        seen = observations()
        for _ in range(18):
            x.ingest_audit(seen, sample(seen, first=False))
        self.assertEqual(x.current, "alternative")
        self.assertEqual(x.transitions[0]["event"], "proposed_revision")
        self.assertFalse(x.transitions[0]["confidence_calibrated"])
        self.assertFalse(x.transitions[0]["investigation"]["causal_proof"])
        snap = json.loads(json.dumps(x.export_state()))
        restored = RecoveryLearner.restore_state(snap)
        self.assertEqual(restored.snapshot(), x.snapshot())
        for _ in range(24):
            restored.ingest_audit(seen, sample(seen, first=True))
        self.assertEqual(restored.current, "broad")
        self.assertTrue(any(event["event"] == "rollback"
                            for event in restored.transitions))
        self.assertEqual(restored.history[0]["sha256"], x.history[0]["sha256"])
        self.assertEqual(len(restored.history), 42)
        self.assertEqual(restored.parameters, FROZEN_CONTROLS)

    def test_no_unearned_switch_without_sufficient_audits(self):
        x = self.make()
        seen = observations()
        for _ in range(7):
            x.ingest_audit(seen, sample(seen, first=False))
        self.assertEqual(x.current, "broad")
        self.assertEqual(x.transitions, [])
        with self.assertRaisesRegex(ValueError, "Evaluator-only"):
            x.act([{**row, "truth": False} for row in seen])

    def test_tampered_recovery_snapshot_fails_closed(self):
        x = self.make()
        seen = observations()
        x.ingest_audit(seen, sample(seen, first=True))
        bad = copy.deepcopy(x.export_state())
        bad["learner"]["history"][0]["audits"][0]["truth"] = False
        with self.assertRaisesRegex(ValueError, "checksum"):
            RecoveryLearner.restore_state(bad)
        bad = copy.deepcopy(x.export_state())
        bad["recovery_controls"]["minimum_lift"] = -1
        with self.assertRaisesRegex(ValueError, "checksum"):
            RecoveryLearner.restore_state(bad)

    def test_sealed_holdout_seeds_dont_overlap_training_or_older_labs(self):
        for mode in ("stable", "reversal", "repeat"):
            training = {seed for _, seed, _ in episodes("sensor", training=True, pattern=mode)}
            holdout = {seed for _, seed, _ in episodes("sensor", training=False, pattern=mode)}
            self.assertFalse(training & holdout)
            self.assertFalse(any(seed in range(41000, 66000) for seed in holdout))
        sets = [{seed for _, seed, _ in episodes("sensor", training=False, pattern=mode)}
                for mode in ("stable", "reversal", "repeat")]
        self.assertFalse(sets[0] & sets[1] | sets[1] & sets[2] | sets[0] & sets[2])

    def test_replay_uses_equal_audit_budget_and_is_deterministic(self):
        catalog = {"baseline": Policy((4, 2, 1, 1)),
                   "broad": Policy((4, 2, 3, 4)),
                   "test_alternative": Policy((8, 0, 0, 0))}
        controls = RecoveryControls()
        first = replay("erp", catalog, controls, training=True, pattern="reversal")
        second = replay("erp", catalog, controls, training=True, pattern="reversal")
        self.assertEqual(first, second)
        self.assertEqual(first["independent_audits_per_policy"], 2 * 78)
        self.assertIn("normal", first["phases"])
        self.assertIn("recovered", first["phases"])
        self.assertTrue(all(event["simulation_only"] for event in first["events"]))

    def test_invalid_recovery_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            RecoveryControls(recent_worlds=0)
        with self.assertRaises(ValueError):
            RecoveryControls(confirmation=0)
        with self.assertRaises(ValueError):
            RecoveryControls(standard_error_multiplier=-1)


if __name__ == "__main__":
    unittest.main()
