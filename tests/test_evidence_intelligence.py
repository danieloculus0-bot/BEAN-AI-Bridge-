"""Independent synthetic tests for BEAN Evidence Lab 003, without live devices."""
import json

import pytest

from experiments.evolution_lab.evidence_intelligence import (
    EvidenceAgent, EvidencePolicy, TRAIN_PROFILES, ADVERSARIAL_PROFILES,
    case_for, evaluate_evidence, evaluate_previous, train_policy, study,
)


def test_verified_change_revises_belief_and_survives_restart():
    policy = EvidencePolicy(attention_threshold=0.35, max_probes=2)
    agent = EvidenceAgent(policy)
    result = agent.observe(0, {"A": 1, "B": 1}, verify=lambda: 1)
    assert result["action"] == "verify"
    assert agent.belief == 1
    assert agent.detected_at == 0
    saved = json.loads(json.dumps(agent.snapshot()))
    resumed = EvidenceAgent(policy, state=saved)
    assert resumed.snapshot() == saved
    assert resumed.evidence[0]["reason"] == "uncertain_change"


def test_never_uses_truth_without_explicit_bounded_probe():
    agent = EvidenceAgent(EvidencePolicy(max_probes=0, independent_check_period=1))
    def forbidden():
        raise AssertionError("Verifier unexpectedly accessed")
    for step in range(5):
        agent.observe(step, {"A": 1, "B": 0}, forbidden)
    assert agent.probes == 0 and agent.belief == 0
    assert not agent.evidence


def test_consistent_sensors_do_not_force_investigation():
    agent = EvidenceAgent(EvidencePolicy(independent_check_period=0))
    def forbidden():
        raise AssertionError("Verifier unexpectedly accessed")
    result = agent.observe(0, {"A": 0, "B": 0}, forbidden)
    assert result["action"] == "observe"


def test_disagreement_creates_falsifiable_source_hypothesis():
    agent = EvidenceAgent(EvidencePolicy(attention_threshold=0.35, min_persistence=1))
    agent.observe(0, {"A": 1, "B": 0}, verify=lambda: 0)
    assert "source_A_unreliable" in agent.hypotheses
    claim = agent.hypotheses["source_A_unreliable"]
    assert claim["status"] == "unresolved"
    assert "verified" in claim["what_would_falsify"].lower()
    assert claim["evidence_refs"]


def test_both_sensors_wrong_raises_common_mode_hypothesis():
    agent = EvidenceAgent(EvidencePolicy(attention_threshold=0.35, max_probes=2))
    agent.observe(0, {"A": 1, "B": 1}, verify=lambda: 0)
    assert agent.belief == 0
    assert "shared_fault" in agent.hypotheses


def test_source_accuracy_is_updated_only_by_verification():
    policy = EvidencePolicy(attention_threshold=0.35, max_probes=5,
                            independent_check_period=1)
    agent = EvidenceAgent(policy)
    prior = agent.source_accuracy("A")
    agent.observe(0, {"A": 0, "B": 0}, verify=lambda: 0)
    assert agent.source_accuracy("A") == prior
    for step in range(1, 4):
        agent.observe(step, {"A": 1, "B": 1}, verify=lambda: 0)
    assert agent.source_accuracy("A") < prior
    assert agent.probes == 3
    assert len(agent.hypotheses["shared_fault"]["evidence_refs"]) == 3


def test_source_reliability_not_equal_claim_of_subjective_consciousness():
    agent = EvidenceAgent(EvidencePolicy())
    assert not any("conscious" in item["statement"].lower() for item in agent.hypotheses.values())
    assert set(agent.snapshot()["reliability"]) == {"A", "B"}


def test_invalid_sensor_rejected_without_verification():
    agent = EvidenceAgent(EvidencePolicy())
    with pytest.raises(ValueError, match="unknown"):
        agent.observe(0, {"not_a_source": 1}, lambda: 1)
    with pytest.raises(ValueError, match="invalid"):
        agent.observe(0, {"A": 9}, lambda: 1)


def test_invalid_profile_rejected():
    with pytest.raises(ValueError, match="unknown"):
        case_for(1, "nonsense")


@pytest.mark.parametrize("profile", ["standard", "correlated_noise", "delayed_sensors", "drifting_a", "stuck_b", "late_shift", "early_shift"])
def test_test_evidence_reports_truth_blind_scores(profile):
    result = evaluate_evidence(EvidencePolicy(), list(range(16000, 16008)), profile)
    assert result["episodes"] == 8
    assert result["restart_state_retained"] == 8
    assert 0 <= result["brier"] <= 1
    assert result["mean_probes"] <= 3
    assert result["mean_hypotheses"] >= 0


def test_drift_profile_changes_reports_not_ground_truth():
    base = case_for(16000, "standard")
    drift = case_for(16000, "drifting_a")
    assert [t[-1] for t in base["timeline"]] == [t[-1] for t in drift["timeline"]]
    assert base["changed"] == drift["changed"]
    assert any(x[0] != y[0] for x, y in zip(base["timeline"], drift["timeline"]))


def test_train_selects_policy_on_separate_seeds_and_is_reproducible():
    best, ranked = train_policy(seed=501, population=8)
    assert best == train_policy(seed=501, population=8)[0]
    assert len(ranked) == 8
    assert ranked == sorted(ranked, key=lambda x: (-x["fitness"], tuple(x["policy"].values())))
    assert set(TRAIN_PROFILES).isdisjoint(ADVERSARIAL_PROFILES)


def test_search_bounds():
    with pytest.raises(ValueError):
        train_policy(population=1)


def test_shifted_event_times_are_not_in_training_schedule():
    late = case_for(16000, "late_shift")
    early = case_for(16000, "early_shift")
    assert late["changed"] == early["changed"]
    assert [x[-1] for x in late["timeline"]] != [x[-1] for x in early["timeline"]]
    assert late["change_at"] in (8, 9, 10)
    assert early["change_at"] in (1, 2)


def test_fixed_comparator_same_as_original_on_training_profiles():
    from experiments.evolution_lab.bridge_evolution import RULE_COMPARATOR, evaluate
    for profile in TRAIN_PROFILES:
        a = evaluate_previous(list(range(16000, 16010)), profile)
        b = evaluate(RULE_COMPARATOR, list(range(16000, 16010)), profile)
        assert a["mean_score"] == b["mean_score"]
        assert a["change_recall"] == b["change_recall"]


def test_source_learning_ablation_is_truth_blind_and_reproducible():
    from dataclasses import replace
    p = EvidencePolicy(max_probes=3)
    without_learning = replace(p, learn_sensor_reliability=False)
    agent = EvidenceAgent(without_learning)
    before = agent.source_accuracy("A")
    agent.observe(0, {"A": 1, "B": 1}, verify=lambda: 0)
    assert agent.source_accuracy("A") == before
    assert agent.reliability["A"][1] > 1
