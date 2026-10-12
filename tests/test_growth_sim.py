"""Lab010 regression tests for executed synthetic strategy learning."""
import random
import tempfile
import unittest
from pathlib import Path

from ezbean.growth_sim import (OnlinePolicy, benchmark, context,
                               exposure, make_world, run_episode)


class GrowthSimulationTests(unittest.TestCase):
    def test_realized_reward_changes_strategy_decision(self):
        agent = OnlinePolicy()
        key = "alternating/up"
        self.assertEqual(agent.choose(key, random.Random(0), explore=False), "momentum")
        agent.learn(key, "momentum", -10)
        agent.learn(key, "reversion", 10)
        self.assertEqual(agent.choose(key, random.Random(0), explore=False), "reversion")

    def test_checkpoint_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "adopted.json"
            policy = OnlinePolicy()
            policy.learn("persistent/up", "buy_hold", 100)
            self.assertEqual(len(policy.save(f)), 64)
            loaded = OnlinePolicy.load(f)
            self.assertEqual(loaded.q, policy.q)
            self.assertEqual(loaded.visits, policy.visits)

    def test_adopted_strategy_is_executed_not_just_logged(self):
        agent = OnlinePolicy()
        agent.q["insufficient"] = {"buy_hold": 10}
        result = run_episode([.01, .02, -.01], agent, record=True)
        self.assertEqual(result["action_ledger"][0]["strategy_executed"], "buy_hold")
        self.assertEqual(result["action_ledger"][0]["exposure"], 1)
        self.assertTrue(result["action_ledger"][0]["traded"])
        self.assertGreater(result["final"], 100)

    def test_no_future_lookahead(self):
        self.assertEqual(context([.01] * 11), "insufficient")
        self.assertEqual(exposure("momentum", []), 0)
        self.assertEqual(exposure("momentum", [-.04]), 0)
        self.assertEqual(exposure("reversion", [-.04]), 1)
        agent = OnlinePolicy()
        # First step is identical even if the unobserved outcome differs.
        a = run_episode([.05, .01], agent, record=True)["action_ledger"][0]
        b = run_episode([-.05, .01], agent, record=True)["action_ledger"][0]
        self.assertEqual((a["context"], a["strategy_executed"], a["exposure"]),
                         (b["context"], b["strategy_executed"], b["exposure"]))

    def test_benchmark_is_replayable_with_disjoint_seeds(self):
        a = benchmark(episodes=8, holdouts=5, period=100)
        b = benchmark(episodes=8, holdouts=5, period=100)
        self.assertEqual(a["average_net_returns"], b["average_net_returns"])
        self.assertTrue(a["checkpoint_reloaded"])
        self.assertEqual(len(a["examples"][0]["result"]["action_ledger"]), 100)
        self.assertIn("untrained", a["average_net_returns"])
        with self.assertRaises(ValueError):
            benchmark(episodes=8, holdouts=8, period=100,
                      train_start=10, test_start=12)


if __name__ == "__main__":
    unittest.main()
