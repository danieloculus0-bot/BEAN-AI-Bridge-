"""BEAN Lab004: falsifiable change-point revision and truth isolation tests."""
import json

import pytest

from experiments.evolution_lab.evidence_intelligence import EvidencePolicy
from experiments.evolution_lab.model_revision_lab004 import (
    POLICY, RevisionAgent, RevisionRules, evaluate_history, run_study,
)


def test_two_unlikely_verified_outcomes_revise_a_stale_source_prior():
    agent = RevisionAgent(POLICY, RevisionRules())
    agent.reliability["A"] = [1.0, 30.0]  # Previously verified as deeply untrustworthy.
    agent._calibrate({"A": 1, "B": 1}, truth=1, step=1)
    assert agent.revisions == []
    agent._calibrate({"A": 1, "B": 1}, truth=1, step=2)
    assert len(agent.revisions) == 1
    assert agent.revisions[0]["source"] == "A"
    assert agent.reliability["A"] == [3.0, 1.0]
    assert "source_A_changed" in agent.hypotheses


def test_ordinary_correct_observations_do_not_trigger_model_reset():
    agent = RevisionAgent(POLICY, RevisionRules())
    for t in range(5):
        agent._calibrate({"A": 1, "B": 1}, truth=1, step=t)
    assert agent.revisions == []
    assert agent.source_surprises == {"A": 0, "B": 0}


def test_disabled_revision_is_control_with_same_evidence():
    control = RevisionAgent(POLICY, RevisionRules(enabled=False))
    control.reliability["A"] = [1.0, 30.0]
    control._calibrate({"A": 1, "B": 1}, truth=1, step=0)
    control._calibrate({"A": 1, "B": 1}, truth=1, step=1)
    assert control.revisions == []
    assert control.reliability["A"] != [3.0, 1.0]


def test_no_verifier_call_without_decision_or_audit():
    agent = RevisionAgent(POLICY, RevisionRules(independent_audits=True))
    def forbidden():
        raise AssertionError("unexpected access to verifier")
    outcome = agent.observe(0, {"A": 0, "B": 0}, forbidden, independent_audit=False)
    assert outcome["action"] == "observe"
    assert agent.probes == 0


def test_independent_check_is_metered_and_generates_verified_evidence():
    agent = RevisionAgent(POLICY, RevisionRules(independent_audits=True))
    result = agent.observe(1, {"A": 0, "B": 0}, lambda: 0, independent_audit=True)
    assert result["action"] == "verify"
    assert result["reason"] == "independently_sampled_audit"
    assert agent.audit_checks == 1
    assert agent.probes == 1
    assert agent.evidence[0]["verified_state"] == 0
    snap = json.loads(json.dumps(agent.snapshot()))
    assert RevisionAgent(POLICY, agent.rules, state=snap).snapshot() == snap


def test_no_extra_audit_when_budget_is_exhausted():
    policy = EvidencePolicy(max_probes=0)
    agent = RevisionAgent(policy, RevisionRules(independent_audits=True))
    def forbidden():
        raise AssertionError("no verification budget")
    agent.observe(1, {"A": 1, "B": 0}, forbidden, independent_audit=True)
    assert agent.probes == 0


def test_change_point_configuration_bounds():
    with pytest.raises(ValueError):
        RevisionRules(surprise_likelihood=0.7)
    with pytest.raises(ValueError):
        RevisionRules(confirmations=0)


def test_history_repeatable_and_truth_separate():
    profiles = ["stuck_b"] * 6 + ["standard"] * 6
    seeds = list(range(47000, 47012))
    a = evaluate_history(profiles, seeds, RevisionRules())
    b = evaluate_history(profiles, seeds, RevisionRules())
    assert a == b
    assert a["restart_state_retained"] == 12
    assert a["overall"]["episodes"] == 12
    assert a["overall"]["mean_probes"] <= 4
    assert a["first_half"]["episodes"] == 6
    assert a["second_half"]["episodes"] == 6


def test_study_has_baselines_and_held_out_regime_shifts():
    study = run_study()
    assert study["seed_window"] == [47000, 47079]
    assert set(study["results"]["stuck_B_then_normal"]) == {
        "remember_without_revision", "revision_after_two_surprises",
        "revision_with_blind_audits", "fresh_each_episode",
    }
    for scenario in study["results"].values():
        for comparison in scenario.values():
            assert comparison["overall"]["episodes"] == 80
            assert comparison["restart_state_retained"] == 80
