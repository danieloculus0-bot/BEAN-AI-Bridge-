"""Strict, synthetic evolution checks that use the real BEAN core's logic gate."""
import pytest

from experiments.evolution_lab.bridge_evolution import (
    BASELINE, RULE_COMPARATOR, Policy, SimulatedAgent, evaluate, evolve, evolve_generalist, generate_case, mutate,
)


def test_experiment_reproducible_for_fixed_seed():
    one = evolve(seed=42, generations=3, population=12)
    two = evolve(seed=42, generations=3, population=12)
    assert one == two
    assert one["label"].startswith("SYNTHETIC_")
    assert one["training_seed_window"][1] < one["heldout_seed_window"][0]


def test_holdout_result_is_recorded_for_all_controls():
    report = evolve(seed=17, generations=3, population=12)
    for name in ("baseline", "rule_comparator", "evolved"):
        assert report[name]["holdout"]["episodes"] == 80
        assert report[name]["holdout"]["restart_state_retained"] == 80
        assert report[name]["holdout"]["mean_probes"] >= 0


def test_evolution_should_not_claim_improvement_without_holdout_evidence():
    report = evolve(seed=1337, generations=6, population=20)
    # Synthetic training must at least beat the deliberately conservative control.
    assert report["evolved"]["training"]["mean_score"] > evaluate(BASELINE, list(range(500, 560)))["mean_score"]
    # Holdout comparison is reported, not forcibly assumed to win.
    assert isinstance(report["evolved"]["holdout"]["mean_score"], float)


def test_agent_saves_verification_evidence_and_resumes_after_interruption():
    policy = Policy(attention_threshold=0.3, confirmations=1, max_probes=2)
    agent = SimulatedAgent(policy)
    agent.observe(0, 1, 1, verify=lambda: 1)
    assert agent.belief == 1
    assert agent.detected_at == 0
    assert agent.evidence[0]["verified_state"] == 1
    recovered = SimulatedAgent(policy, saved_state=agent.snapshot())
    assert recovered.snapshot() == agent.snapshot()
    assert recovered._streak == 0


def test_verified_unchanged_state_does_not_become_false_belief():
    policy = Policy(attention_threshold=0.3, confirmations=1, max_probes=1)
    agent = SimulatedAgent(policy)
    agent.observe(0, 1, 1, verify=lambda: 0)
    assert agent.belief == 0
    assert agent.false_probes == 1
    assert agent.probes == 1
    agent.observe(1, 1, 1, verify=lambda: 1)
    assert agent.belief == 0
    assert agent.probes == 1


def test_invalid_search_size_rejected():
    with pytest.raises(ValueError):
        evolve(generations=0)


def test_unseen_fault_profiles_are_scored_without_selection_leakage():
    report = evolve(seed=1337, generations=3, population=12)
    assert set(report["out_of_distribution"]) == {"correlated_noise", "delayed_sensors"}
    for group in report["out_of_distribution"].values():
        for mode in ("baseline", "rule_comparator", "evolved"):
            assert group[mode]["episodes"] == 80
            assert group[mode]["restart_state_retained"] == 80


def test_correlated_fault_changes_sensor_evidence_but_not_ground_truth():
    ordinary = generate_case(12000, "standard")
    noisy = generate_case(12000, "correlated_noise")
    assert ordinary["change_at"] == noisy["change_at"]
    assert ordinary["changed"] == noisy["changed"]
    assert [x[2] for x in ordinary["timeline"]] == [x[2] for x in noisy["timeline"]]
    assert [x[:2] for x in ordinary["timeline"]] != [x[:2] for x in noisy["timeline"]]


def test_unknown_sensor_profile_fails_closed():
    with pytest.raises(ValueError):
        generate_case(1, "unknown")


def test_agent_adapts_confirmation_requirement_after_false_probe():
    policy = Policy(attention_threshold=0.3, confirmations=1, max_probes=3,
                    learn_from_false_probes=True)
    agent = SimulatedAgent(policy)
    agent.observe(0, 1, 1, verify=lambda: 0)
    assert agent.false_probes == 1 and agent.probes == 1
    agent.observe(1, 1, 1, verify=lambda: 1)
    assert agent.probes == 1
    agent.observe(2, 1, 1, verify=lambda: 1)
    assert agent.probes == 2
    assert agent.belief == 1


def test_generalist_lineage_reports_independent_mixed_holdout():
    result = evolve_generalist(seed=917, generations=3, population=12)
    assert set(result["by_profile"]) == {"standard", "correlated_noise", "delayed_sensors"}
    assert result["train_seed_window"][1] < result["holdout_seed_window"][0]
    for profile, scores in result["by_profile"].items():
        assert scores["generalist"]["episodes"] == 80
        assert scores["fixed_comparator"]["episodes"] == 80
    assert result == evolve_generalist(seed=917, generations=3, population=12)
