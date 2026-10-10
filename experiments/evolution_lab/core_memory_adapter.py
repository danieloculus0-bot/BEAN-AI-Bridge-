"""Replay verified synthetic evidence into actual BEAN cognition and SQLite.

BEAN's real EventLogger, EpistemicGuard, UncertaintyGarden,
FalsificationEngine and reasoning context are used here, not stand-ins.
This adapter is explicit and off by default; no hardware or network I/O.
"""
from __future__ import annotations

import json
from pathlib import Path


def replay_verified_case(*, evidence: list[dict], hypotheses: dict, db_path: str) -> dict:
    from bean.memory.store import _local, init_store, get_store
    from bean.memory.identity import bootstrap_identity
    from bean.memory.session import begin_session, end_session
    from bean.memory.origin import ORIGIN_KEY, ensure_origin_records
    from bean.memory.event_logger import log_event, EventType, Source
    from bean.cognition.epistemic_guard import EpistemicGuard, CandidateClaim
    from bean.cognition.uncertainty_garden import UncertaintyGarden, UncertaintyRecord
    from bean.cognition.falsification import FalsificationEngine
    from bean.reasoning.context_builder import build_reasoning_context

    if getattr(_local, "conn", None):
        _local.conn.close()
        _local.conn = None
    if not db_path or str(Path(db_path).resolve()) == ":memory:":
        raise ValueError("explicit sandbox memory file required")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    init_store(db_path)
    bootstrap_identity()
    session_uuid = begin_session()
    ensure_origin_records(session_uuid)
    guard = EpistemicGuard()
    garden = UncertaintyGarden()
    engine = FalsificationEngine()

    observation_ids = []
    for observation in evidence:
        if "verified_state" not in observation:
            raise ValueError("unverified observation cannot enter verified ledger")
        event_id = log_event(
            session_uuid, EventType.OBSERVATION,
            f"Lab verified a simulated state at step {observation['step']}",
            Source.SYSTEM, subtype="lab_verification",
            data={"synthetic": True, "verification": dict(observation)},
        )
        observation_ids.append(event_id)

    audits = []
    uncertainty_ids = []
    for key, hypothesis in sorted(hypotheses.items()):
        refs = [str(x) for x in hypothesis.get("evidence_refs", [])]
        claim = CandidateClaim(
            key=f"research.lab.{key}",
            content=str(hypothesis["statement"]),
            source_type="synthetic_experiment",
            source_ref="lab:evidence_intelligence",
            confidence=0.5,
            evidence=refs,
            falsification_path=str(hypothesis["what_would_falsify"]),
        )
        audit = guard.audit(claim)
        audits.append(audit.to_dict())
        question = UncertaintyRecord(
            question=f"Is this explanation supported? {hypothesis['statement']}",
            what_would_resolve_it=str(hypothesis["what_would_falsify"]),
            significance=0.65,
        )
        garden.plant(question, [
            ("The proposed failure mode is present", 0.5),
            ("The evidence is explained by random measurement noise", 0.5),
        ])
        uncertainty_ids.append(question.uncertainty_id)
        garden.review(question.uncertainty_id)

    rule = engine.add_missing_recent_event_rule(
        claim_key="research.lab.has_verification",
        event_type="observation",
        subtype="lab_verification",
        max_age_minutes=30,
    )
    result = engine.check_all(session_uuid)
    packet = build_reasoning_context(session_uuid, packet_type="synthetic_evidence_lab")
    history = packet["context"]["origin_covenant"]["history"]
    summary = {
        "session_uuid": session_uuid,
        "verified_events": len(observation_ids),
        "hypotheses": len(hypotheses),
        "uncertainties_planted": len(uncertainty_ids),
        "epistemic_verdicts": [a["verdict"] for a in audits],
        "falsification_results": [{
            "claim_key": r.claim_key,
            "falsified": bool(r.falsified),
            "action": r.action_taken,
        } for r in result],
        "missing_verification_falsified": next(
            r.falsified for r in result if r.rule_id == rule.rule_id
        ),
        "origin_version_in_reasoning": history.get("version"),
        "expected_origin_version": ORIGIN_KEY,
        "reasoning_packet_id": packet["packet_id"],
        "motion_enabled": False,
        "source": "BEAN core real SQLite and cognition",
    }
    end_session(session_uuid, reason="clean", notes="Synthetic laboratory replay")
    return summary
