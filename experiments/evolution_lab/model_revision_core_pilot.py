"""Lab004 integration pilot: preserve a falsifiable change of mind in real BEAN.

All observations are synthetic, each verification explicitly requested by
BEAN's attention gate. The memory replay uses actual BEAN Core SQLite cognition.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from experiments.evolution_lab.evidence_intelligence import EvidencePolicy
from experiments.evolution_lab.model_revision_lab004 import RevisionAgent, RevisionRules
from experiments.evolution_lab.core_memory_adapter import replay_verified_case


def run_pilot(db_path: str) -> dict:
    agent = RevisionAgent(
        EvidencePolicy(
            attention_threshold=0.35,
            min_persistence=1, max_probes=4,
            probe_confidence=0.53, independent_check_period=0,
        ),
        RevisionRules(),
    )
    # Simulate BEAN arriving with an obsolete but historically learned prior:
    # source A used to be unreliable. The current verified observations show
    # it is now correct, requiring more than one surprise before revision.
    agent.reliability["A"] = [1.0, 30.0]

    results = [
        agent.observe(step, {"A": 1, "B": 0}, verify=lambda: 1)
        for step in (0, 1)
    ]
    if len(agent.revisions) != 1:
        raise AssertionError("model did not register exactly one verified revision")
    if any(x["action"] != "verify" for x in results):
        raise AssertionError("model did not request a metered inspection")

    core = replay_verified_case(
        evidence=agent.evidence,
        hypotheses=agent.hypotheses,
        db_path=db_path,
    )
    if core["verified_events"] != 2:
        raise AssertionError("real BEAN memory did not receive both verified observations")
    if core["hypotheses"] != len(agent.hypotheses):
        raise AssertionError("real BEAN cognition lost hypotheses")
    if core["origin_version_in_reasoning"] != core["expected_origin_version"]:
        raise AssertionError("real BEAN reasoning packet lost founding origin")
    return {
        "label": "LAB004_VERIFIED_SOURCE_MODEL_REVISION_REPLAY",
        "revision": agent.revisions[0],
        "agent_hypotheses": sorted(agent.hypotheses),
        "inspection_actions": [x["action"] for x in results],
        "core": core,
        "note": "Real core storage and reasoning; entirely synthetic inputs; no external actions.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("lab004-core-pilot.json"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="bean_lab004_") as temp:
        result = run_pilot(str(Path(temp) / "bean-memory.db"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
