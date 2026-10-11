"""Regression tests for honest evaluation, train/holdout isolation and transfer."""
import unittest
import importlib.util
from experiments.broad_improvement.lab012 import (
    BASELINE, DOMAINS, Policy, evaluate, run, scenario, train,
)


class BroadImprovementTests(unittest.TestCase):
    def test_repeatable_training(self):
        self.assertEqual(train(DOMAINS), train(DOMAINS))

    def test_training_does_not_access_evaluation_seeds(self):
        import inspect
        text = inspect.getsource(train)
        self.assertNotIn('21000', text)
        self.assertNotIn('30000', text)

    def test_agent_observations_have_evaluator_private_truth(self):
        episode = scenario('erp', 777)
        self.assertEqual(len(episode), 12)
        self.assertNotIn('truth', episode[0]['features'])
        self.assertEqual(set(episode[0]['features']), {'surprise', 'contradiction', 'coverage_gap', 'echo_risk'})

    def test_frozen_baseline_and_no_automatic_promotion(self):
        a = run()
        b = run()
        self.assertEqual(a, b)
        self.assertEqual(a['baseline_policy'], BASELINE)
        self.assertEqual(a['core_main_unchanged'], True)
        self.assertIn(a['verdict'], ('BROAD_IMPROVEMENT_NOT_DEMONSTRATED',
                                     'BROAD_IMPROVEMENT_DEMONSTRATED_IN_SYNTHETIC_LAB'))
        for domain in DOMAINS:
            self.assertEqual(a['ordinary_holdout']['candidate'][domain]['records'], 80 * 12)
            self.assertEqual(a['shifted_holdout']['candidate'][domain]['records'], 80 * 12)
            self.assertEqual(a['leave_one_domain_out'][domain]['candidate']['records'], 80 * 12)

    def test_holdout_evaluator_is_not_perfect_or_fabricated(self):
        test = evaluate(Policy(BASELINE), 'sensor', range(21000, 21005))
        self.assertEqual(test['true_positive'] + test['false_positive'], 5 * 3)
        self.assertEqual(test['records'], 5 * 12)
        self.assertGreater(test['false_negative'], 0)

    @unittest.skipUnless(importlib.util.find_spec("bean") is not None,
                         "Core is checked out and required by the dedicated Lab012 workflow")
    def test_core_attends_and_proposals_cannot_execute(self):
        from experiments.broad_improvement.lab012 import core_receipt
        result = core_receipt({'isolated': True})
        self.assertEqual(result['attention_entries'], 12)
        self.assertEqual(result['governor_status'], 'proposed')
        self.assertEqual(result['execution_permission'], 'proposal_only')
        self.assertFalse(result['auto_executed'])


if __name__ == '__main__':
    unittest.main()
