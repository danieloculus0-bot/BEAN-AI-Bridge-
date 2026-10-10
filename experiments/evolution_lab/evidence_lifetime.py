"""BEAN Evidence Lab 003b: does source reliability transfer across experience?

This measures a sequence of separate synthetic episodes under one continuing
source environment. Only independently verified feedback carries forward.
Scenario ground truth stays inside the evaluation harness.
"""
from __future__ import annotations

import json
from dataclasses import asdict, replace

from experiments.evolution_lab.evidence_intelligence import (
    EvidenceAgent, EvidencePolicy, case_for,
)


def evaluate_lifetime(
    policy: EvidencePolicy, seeds: list[int], profiles: list[str], *,
    carry_calibration: bool = True,
) -> dict:
    if len(seeds) != len(profiles) or not seeds:
        raise ValueError("worlds and seeds must be nonempty and aligned")
    calibration = None
    totals = {"hits": 0, "changes": 0, "points": 0.0, "probes": 0, "false_probes": 0}
    segments = []
    squared = count = 0
    for i, (seed, profile) in enumerate(zip(seeds, profiles)):
        case = case_for(seed, profile)
        agent = EvidenceAgent(policy)
        if carry_calibration and calibration is not None:
            agent.reliability = {source: list(value) for source, value in calibration.items()}
        for step, (a, b, truth) in enumerate(case["timeline"]):
            agent.observe(step, {"A": a, "B": b}, verify=lambda value=truth: value)
            squared += (agent.forecasts[-1]["p_state_1"] - truth) ** 2
            count += 1
            if step == 6:
                snap = json.loads(json.dumps(agent.snapshot()))
                agent = EvidenceAgent(policy, snap)
                assert agent.snapshot() == snap
        if carry_calibration:
            calibration = {source: list(v) for source, v in agent.reliability.items()}
        hit = bool(case["changed"] and agent.belief == 1 and agent.detected_at is not None)
        points = 0.0
        if case["changed"]:
            totals["changes"] += 1
            if hit:
                totals["hits"] += 1
                points = 4 - 0.2 * max(0, agent.detected_at - case["change_at"])
            else:
                points = -2
        else:
            points = 3 if agent.belief == 0 else -3
        points -= 0.17 * agent.probes + 0.45 * agent.false_probes
        totals["points"] += points
        totals["probes"] += agent.probes
        totals["false_probes"] += agent.false_probes
        segments.append({
            "world": i, "profile": profile, "change": bool(case["changed"]),
            "hit": hit, "score": round(points, 4),
            "probes": agent.probes,
            "source_reliability": {source: round(agent.source_accuracy(source), 4)
                                   for source in ("A", "B")},
        })
    n = len(seeds)

    def aggregate(rows: list[dict]) -> dict:
        changes = sum(x["change"] for x in rows)
        hits = sum(x["hit"] for x in rows)
        return {
            "change_recall": round(hits / changes, 4) if changes else None,
            "mean_score": round(sum(x["score"] for x in rows) / len(rows), 4),
            "mean_probes": round(sum(x["probes"] for x in rows) / len(rows), 4),
        }

    half = max(1, n // 2)
    return {
        "worlds": n,
        "profiles": list(dict.fromkeys(profiles)),
        "carry_calibration": carry_calibration,
        "total": aggregate(segments),
        "first_half": aggregate(segments[:half]),
        "second_half": aggregate(segments[half:]),
        "brier": round(squared / count, 4),
        "final_source_reliability": segments[-1]["source_reliability"],
        "first_5": segments[:5],
        "last_5": segments[-5:],
    }


def longitudinal_study() -> dict:
    seeds = list(range(23000, 23080))
    policy = EvidencePolicy(
        attention_threshold=0.45, probe_confidence=0.53, max_probes=4,
        min_persistence=3, reliability_decay=0.9,
        independent_check_period=0,
    )
    worlds = {
        "stable_standard": ["standard"] * len(seeds),
        "stable_stuck_b": ["stuck_b"] * len(seeds),
        "stable_drifting_a": ["drifting_a"] * len(seeds),
        "stuck_b_to_standard": ["stuck_b"] * 40 + ["standard"] * 40,
        "standard_to_stuck_b": ["standard"] * 40 + ["stuck_b"] * 40,
    }
    return {
        "label": "LONGITUDINAL_SENSOR_CALIBRATION_SYNTHETIC",
        "seed_window": [min(seeds), max(seeds)],
        "policy": asdict(policy),
        "results": {
            world: {
                "persistent": evaluate_lifetime(policy, seeds, profiles, carry_calibration=True),
                "fresh_each_time": evaluate_lifetime(policy, seeds, profiles, carry_calibration=False),
                "unlearned": evaluate_lifetime(
                    replace(policy, learn_sensor_reliability=False),
                    seeds, profiles, carry_calibration=True,
                ),
            } for world, profiles in worlds.items()
        },
        "limits": [
            "Persistent knowledge consists of verified source statistics only.",
            "Each episode starts with a fresh environmental belief, action budget and hypotheses.",
            "The verifier remains a synthetic oracle; this is not a physical deployment.",
            "Verification is selectively sampled, so calibration may become biased.",
        ],
    }
