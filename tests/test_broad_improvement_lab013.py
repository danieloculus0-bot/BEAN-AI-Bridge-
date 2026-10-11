"""Lab 013 adversarial and integrity tests: labels cannot leak into decisions."""
from __future__ import annotations

import copy
import json
import unittest

from experiments.broad_improvement.lab012 import Policy, scenario
from experiments.broad_improvement.lab013 import (
    AdaptiveLearner, LearningParameters, action_reward, ranking, simulate, timeline
)


def synthetic_case():
    # Two competing learned explanations choose different groups.
    observations = []
    for i in range(12):
        observations.append({"id": str(i), "features": {
            "surprise": 1.0 if i < 3 else 0.05,
            "contradiction": 1.0 if 3 <= i < 6 else 0.05,
            "coverage_gap": 0.05, "echo_risk": 0.05}})
    return observations


class AdaptiveLearningTests(unittest.TestCase):
    def params(self):
        return LearningParameters(audits_per_world=4, evidence_window=8,
                                  minimum_audits=32, advantage_margin=0.5,
                                  confirm_windows=1, cooldown_worlds=0)

    def make(self):
        return AdaptiveLearner(
            {"broad": Policy((8, 0, 0, 0)), "baseline": Policy((0, 8, 0, 0))},
            self.params())

    def test_no_evaluator_truth_or_phase_leak(self):
        learner = self.make()
        world = scenario("sensor", 99, shifted=True)
        with self.assertRaisesRegex(ValueError, "Evaluator-only"):
            learner.act(world)
        visible = [{"id": x["id"], "features": x["features"]} for x in world]
        result = learner.act(visible)
        self.assertEqual(len(result), 3)
        with self.assertRaisesRegex(ValueError, "independent audit count"):
            learner.ingest_audit(visible, [{"id": world[0]["id"], "truth": True}])

    def test_audit_contract_rejects_unsupported_labels(self):
        learner = self.make()
        visible = synthetic_case()
        with self.assertRaisesRegex(ValueError, "distinct"):
            learner.ingest_audit(visible, [{"id": "0", "truth": True}] * 4)
        with self.assertRaisesRegex(ValueError, "labels must be bool"):
            learner.ingest_audit(visible, [{"id": str(x), "truth": 1} for x in (0, 3, 5, 7)])

    def test_change_detection_and_recovery_uses_audits_only(self):
        brain = self.make()
        visible = synthetic_case()
        sampled_ids = (0, 1, 3, 4)
        for _ in range(12):
            # The broad policy's preferred evidence has become unreliable.
            labels = [{"id": str(i), "truth": i in (3, 4)} for i in sampled_ids]
            brain.ingest_audit(visible, labels)
        self.assertEqual(brain.current, "baseline")
        assert brain.transitions
        self.assertEqual(brain.transitions[0]["from"], "broad")
        self.assertEqual(brain.transitions[0]["to"], "baseline")
        self.assertTrue(brain.transitions[0]["evidence_ids"])
        investigation = brain.transitions[0]["investigation"]
        self.assertFalse(investigation["causal_proof"])
        self.assertEqual(investigation["sampling"], "independent_uniform_audits_only")
        self.assertEqual(len(investigation["feature_checks"]), 4)
        self.assertTrue(any(x["status"] == "insufficient_evidence"
                            for x in investigation["feature_checks"]))
        state = json.loads(json.dumps(brain.export_state()))
        recovered = AdaptiveLearner.restore_state(state)
        self.assertEqual(recovered.snapshot(), brain.snapshot())
        self.assertEqual(recovered.act(visible), brain.act(visible))
        for _ in range(20):
            labels = [{"id": str(i), "truth": i in (0, 1)} for i in sampled_ids]
            recovered.ingest_audit(visible, labels)
        self.assertEqual(recovered.current, "broad")
        self.assertTrue(any(x["event"] == "rollback" for x in recovered.transitions))
        self.assertGreater(len(recovered.history), len(state["history"]))
        self.assertEqual(recovered.history[0]["sha256"], brain.history[0]["sha256"])
        self.assertIn("broad", recovered.retired)

    def test_restart_detects_corruption_in_evidence(self):
        learner = self.make()
        visible = synthetic_case()
        learner.ingest_audit(visible, [{"id": str(i), "truth": i < 3} for i in (0, 1, 3, 4)])
        state = learner.export_state()
        tampered = copy.deepcopy(state)
        tampered["history"][0]["audits"][0]["truth"] = False
        with self.assertRaisesRegex(ValueError, "integrity"):
            AdaptiveLearner.restore_state(tampered)
        inside = copy.deepcopy(state)
        inside["history"][0]["sha256"] = "invalid"
        from experiments.broad_improvement.lab013 import _fingerprint
        inside["sha256"] = _fingerprint({k: v for k, v in inside.items() if k != "sha256"})
        with self.assertRaisesRegex(ValueError, "corrupted"):
            AdaptiveLearner.restore_state(inside)

    def test_honest_evaluator_rewards_and_fixed_inspection_budget(self):
        visible = synthetic_case()
        selected = ranking(visible, Policy((8, 0, 0, 0)))
        self.assertEqual(len(selected), 3)
        world = [{**x, "truth": int(x["id"]) in (3, 4)} for x in visible]
        self.assertLess(action_reward(selected, world),
                        action_reward(ranking(visible, Policy((0, 8, 0, 0))), world))

    def test_timeline_shift_is_not_in_visible_observations(self):
        phases = timeline("sensor", training=False)
        self.assertEqual([sum(x[0] == name for x in phases)
                          for name in ("initial", "changed", "recovered")], [30, 50, 30])
        self.assertTrue(all(x[1] not in range(1000, 1040) for x in phases))


if __name__ == "__main__":
    unittest.main()
