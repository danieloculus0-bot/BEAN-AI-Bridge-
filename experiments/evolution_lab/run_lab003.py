"""One-command BEAN Lab 003 reproducible synthetic evaluation."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from experiments.evolution_lab.evidence_intelligence import (
    EvidenceAgent, EvidencePolicy, study,
)
from experiments.evolution_lab.core_memory_adapter import replay_verified_case


def run(out: Path) -> dict:
    results = study()
    pilot = EvidenceAgent(EvidencePolicy(attention_threshold=0.35))
    pilot.observe(0, {"A": 1, "B": 1}, verify=lambda: 0)
    pilot.observe(1, {"A": 1, "B": 0}, verify=lambda: 0)
    # A disposable DB proves actual BEAN core receives the records.
    with tempfile.TemporaryDirectory(prefix="bean_evidence_") as scratch:
        results["real_core_integration"] = replay_verified_case(
            evidence=pilot.evidence,
            hypotheses=pilot.hypotheses,
            db_path=str(Path(scratch) / "bean_cognition.db"),
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("evidence-lab-report.json"))
    args = parser.parse_args()
    report = run(args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
