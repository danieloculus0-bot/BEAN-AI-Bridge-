"""Longitudinal probes distinguish retained evidence from hidden truth."""
import pytest
from dataclasses import replace

from experiments.evolution_lab.evidence_lifetime import evaluate_lifetime
from experiments.evolution_lab.evidence_intelligence import EvidencePolicy


def test_sequence_validation():
    with pytest.raises(ValueError):
        evaluate_lifetime(EvidencePolicy(), [], [])
    with pytest.raises(ValueError):
        evaluate_lifetime(EvidencePolicy(), [1], ["standard", "stuck_b"])


def test_verified_source_memory_survives_world_boundaries():
    policy = EvidencePolicy(attention_threshold=0.35, max_probes=4)
    seeds = list(range(23000, 23012))
    profiles = ["stuck_b"] * len(seeds)
    persistent = evaluate_lifetime(policy, seeds, profiles, carry_calibration=True)
    fresh = evaluate_lifetime(policy, seeds, profiles, carry_calibration=False)
    assert persistent["worlds"] == fresh["worlds"] == 12
    assert persistent["profiles"] == fresh["profiles"] == ["stuck_b"]
    assert persistent["carry_calibration"] is True
    assert fresh["carry_calibration"] is False
    assert 0 <= persistent["brier"] <= 1
    assert persistent["final_source_reliability"] != fresh["final_source_reliability"]


def test_unlearned_calibration_cannot_change_source_priors():
    p = replace(EvidencePolicy(attention_threshold=0.35), learn_sensor_reliability=False)
    results = evaluate_lifetime(p, list(range(23000, 23012)), ["stuck_b"] * 12)
    assert all(
        row["source_reliability"] == {"A": 0.6667, "B": 0.6667}
        for row in results["first_5"] + results["last_5"]
    )


def test_environmental_regime_shift_retains_only_verification_knowledge():
    p = EvidencePolicy(attention_threshold=0.35, max_probes=4)
    seeds = list(range(23000, 23020))
    worlds = ["stuck_b"] * 10 + ["standard"] * 10
    r = evaluate_lifetime(p, seeds, worlds)
    assert r["profiles"] == ["stuck_b", "standard"]
    assert r["first_half"]["change_recall"] is not None
    assert r["second_half"]["change_recall"] is not None
    assert r["total"]["mean_probes"] <= 4
    assert r == evaluate_lifetime(p, seeds, worlds)
