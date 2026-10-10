"""BEAN bridge smoke-test lab: evidence-based, fail-closed release gates.

Consumes machine-produced JSON outcomes. Does not manufacture observations or
call an LLM to make acceptance decisions. Stores append-only observations through
the existing BEAN SQLite ledger and verifies repeated replay determinism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .core import Observation
from .store import Ledger

REQUIRED_PHASES = {
    "python": ("package_install", "cli_smoke"),
    "iso": ("package_install", "boot_structure", "guest_boot", "first_run"),
    "release": ("package_install", "boot_structure", "guest_boot", "first_run", "persistent_reboot"),
}


def assess(report: dict, required: tuple[str, ...]) -> dict:
    if not isinstance(report, dict) or not isinstance(report.get("checks"), dict):
        raise ValueError("Expected report object with checks dictionary")
    checks = report["checks"]
    outcomes = {}
    for key in required:
        evidence = checks.get(key)
        if not isinstance(evidence, dict):
            outcomes[key] = {"status": "missing", "evidence": ""}
            continue
        status = str(evidence.get("status", "missing")).lower()
        proof = evidence.get("evidence", "")
        # A claimed PASS without specific machine evidence is NOT a PASS.
        if status == "pass" and (not isinstance(proof, str) or not proof.strip()):
            status = "unproven"
        elif status not in {"pass", "fail", "skip", "missing", "unproven"}:
            status = "unproven"
        outcomes[key] = {"status": status, "evidence": proof if isinstance(proof, str) else ""}
    good = sum(e["status"] == "pass" for e in outcomes.values())
    return {
        "schema": "bean.smoke.v1",
        "project": report.get("project", "unknown"),
        "phase": report.get("phase", "unknown"),
        "verdict": "PASS" if good == len(required) else "FAIL",
        "passed": good,
        "required": len(required),
        "evidence_ratio": round(good / len(required), 6),
        "checks": outcomes,
        "confidence_note": "evidence_ratio is coverage, not probability of correctness",
    }


def evaluate(report: dict, phase: str, ledger_path: Path, repetitions: int = 3) -> dict:
    if phase not in REQUIRED_PHASES:
        raise ValueError(f"Unknown phase: {phase}")
    if repetitions < 2 or repetitions > 100:
        raise ValueError("repetitions must be 2..100")
    result = assess(report, REQUIRED_PHASES[phase])
    report_blob = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(report_blob.encode()).hexdigest()
    obs = Observation.from_dict({
        "source": "venvwin-smoke-lab",
        "event_id": digest,
        "entity_type": "software_smoke",
        "entity_id": str(report.get("project", "venvwin")),
        "observed_at": str(report["observed_at"]),
        "payload": {"report": report, "assessment": result, "digest": digest},
    })
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(ledger_path)
    try:
        additions = []
        for _ in range(repetitions):
            additions.append(ledger.ingest(obs))
            # Every replay has to produce the same report, regardless of history.
            assert assess(report, REQUIRED_PHASES[phase]) == result
            replay = [x for x in ledger.replay() if x.event_id == digest]
            assert len(replay) == 1
            assert replay[0].payload["assessment"] == result
        assert additions[1:] == [False] * (repetitions - 1)
    finally:
        ledger.close()
    return {**result, "sha256": digest, "repetitions": repetitions,
            "new_observation": additions[0], "ledger": str(ledger_path)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BEAN bridge evidence smoke-test lab")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--phase", choices=tuple(REQUIRED_PHASES), required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        verdict = evaluate(report, args.phase, args.ledger, args.repeat)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(verdict, indent=2))
        return 0 if verdict["verdict"] == "PASS" else 1
    except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
        print(f"BEAN LAB FAIL CLOSED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
