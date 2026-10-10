"""Exercise the actual BEAN Brain modules with controlled synthetic evidence."""
import pytest

from experiments.evolution_lab.core_memory_adapter import replay_verified_case
from experiments.evolution_lab.evidence_intelligence import EvidenceAgent, EvidencePolicy


def test_real_core_replays_evidence_into_memory_and_reasoning(tmp_path):
    a = EvidenceAgent(EvidencePolicy(attention_threshold=0.35))
    a.observe(0, {"A": 1, "B": 1}, verify=lambda: 0)
    assert a.evidence
    assert a.hypotheses
    summary = replay_verified_case(
        evidence=a.evidence, hypotheses=a.hypotheses,
        db_path=str(tmp_path / "bean_real_core.db"),
    )
    assert summary["verified_events"] == 1
    assert summary["hypotheses"] >= 1
    assert summary["uncertainties_planted"] == summary["hypotheses"]
    assert all(v == "approved" for v in summary["epistemic_verdicts"])
    assert summary["missing_verification_falsified"] is False
    assert summary["origin_version_in_reasoning"] == summary["expected_origin_version"]
    assert summary["reasoning_packet_id"].startswith("packet_")
    assert summary["motion_enabled"] is False


def test_missing_verification_is_falsifiable_in_real_core(tmp_path):
    summary = replay_verified_case(
        evidence=[],
        hypotheses={},
        db_path=str(tmp_path / "no_evidence.db"),
    )
    assert summary["verified_events"] == 0
    assert summary["missing_verification_falsified"] is True


def test_unverified_input_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unverified"):
        replay_verified_case(
            evidence=[{"step": 0, "reading": 1}],
            hypotheses={},
            db_path=str(tmp_path / "reject.db"),
        )
