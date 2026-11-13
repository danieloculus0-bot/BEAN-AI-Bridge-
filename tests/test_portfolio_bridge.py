"""Proof of real separate BEAN Core replay from Bridge learning-cycle metadata."""
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from ezbean.portfolio_bridge import BridgePortfolioLedger


class BridgePortfolioTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        core=os.environ.get("BEAN_CORE_DIR")
        if not core:
            self.skipTest("BEAN research Core checkout unavailable")
        self.bridge = BridgePortfolioLedger(core,Path(self.temp.name)/"memory.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def test_cycle_is_memory_not_false_training(self):
        outcome = SimpleNamespace(cycle_id="cycle_lab009_a",
                  concept="material forecast",result_status="answerable",
                  system_answer="private customer information",
                  model_accepted=True)
        self.assertTrue(self.bridge.remember_cycle(outcome)["new"])
        self.assertFalse(self.bridge.remember_cycle(outcome)["new"])
        self.assertEqual(self.bridge.verify()["events"],1)
        self.assertEqual(self.bridge.verify()["q_entries"],0)
        self.assertNotIn("private customer information",str(self.bridge.context()))

    def test_independent_reward_is_persistent_and_replayable(self):
        self.bridge.learn_from_evaluation(
            evaluation_id="test_cycle_001",concept="price/delta",
            action="investigate",reward=2.0,next_concept="price/reconciled",
            evidence_ref="test://holdout-001")
        self.assertEqual(self.bridge.verify()["q_entries"],1)
        self.assertFalse(self.bridge.learn_from_evaluation(
            evaluation_id="test_cycle_001",concept="price/delta",
            action="investigate",reward=2.0,next_concept="price/reconciled",
            evidence_ref="test://holdout-001")["new"])
        self.assertEqual(self.bridge.verify()["events"],1)
        with self.assertRaises(ValueError):
            self.bridge.learn_from_evaluation(
                evaluation_id="bad",concept="price/delta",action="investigate",
                reward=2,next_concept="price/reconciled",
                evidence_ref="test://holdout-002",kind="unverified")


if __name__ == "__main__":
    unittest.main()
