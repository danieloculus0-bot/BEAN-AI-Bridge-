"""BEAN-hosted, bounded autonomous source-improvement experiment for the Bridge.

A trusted host scans a fixed set of production files, records reproducible
evidence, asks BEAN to rank candidates, then independently tests and applies
ONE narrow patch on a disposable/CI checkout. All other actions are denied.

This is real source modification, not unrestricted LLM code generation.
The independent GitHub workflow owns pushing and opening a reviewable PR.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

from bean.optimization.governor import SelfOptimizationGovernor
from bean.optimization.selection import ImprovementOpportunity, rank_improvements

ROOT = Path(__file__).resolve().parents[1]
STORE = Path("src/ezbean/store.py")
CORE = Path("src/ezbean/core.py")
LEDGER_TEST = Path("tests/test_agent_ledger_validation.py")
CACHE_TEST = Path("tests/test_agent_timestamp_cache.py")
APPROVED_WRITES = frozenset({STORE, CORE, LEDGER_TEST, CACHE_TEST})


def digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def python_run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # The checkout BEAN package must be independently supplied by the host.
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=180,
    )


def regression() -> dict:
    run = python_run("-m", "unittest", "discover", "-s", "tests", "-v")
    return {"passed": run.returncode == 0, "exit_code": run.returncode,
            "summary": (run.stderr + run.stdout)[-1200:]}


def ledger_witness() -> bool:
    """True only if the old ledger demonstrably accepts an invalid timestamp."""
    code = (
        "from ezbean.store import Ledger\n"
        "from ezbean.core import Observation\n"
        "l=Ledger()\n"
        "l.ingest(Observation('source','event','job','id','not-a-timestamp',{'due_date':'2026-10-01'}))\n"
        "assert len(l.replay()) == 1\n"
    )
    return python_run("-c", code).returncode == 0


def timestamp_parses() -> int | None:
    code = (
        "import ezbean.core as c\n"
        "from datetime import datetime,timezone\n"
        "from ezbean.core import Observation\n"
        "real=c.utc_datetime\n"
        "calls=[]\n"
        "def counted(v):\n"
        " calls.append(v)\n"
        " return real(v)\n"
        "c.utc_datetime=counted\n"
        "events=[Observation('s',str(i),'job','one','2026-10-01T00:00:00+00:00',{}) for i in range(8)]\n"
        "c.latest_entities(events,datetime(2026,10,10,tzinfo=timezone.utc))\n"
        "print(len(calls))\n"
    )
    result = python_run("-c", code)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def method_line(source: str, name: str) -> int | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    return next((n.lineno for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == name), None)


def discover() -> list[ImprovementOpportunity]:
    opportunities = []
    store = (ROOT / STORE).read_text(encoding="utf-8")
    line = method_line(store, "_ingest_uncommitted")
    if (line is not None and
        "serialized = json.dumps(observation.payload" in store and
        "observation = Observation.from_dict({" not in store and
        not (ROOT / LEDGER_TEST).exists() and ledger_witness()):
        opportunities.append(ImprovementOpportunity(
            "validate_unchecked_ledger_observations",
            "Prevent invalid manually constructed ERP events from contaminating durable evidence",
            (f"{STORE}:{line}", "witness:invalid_observed_at_accepted"),
            impact=5, reproducibility=5, confidence=1.0, risk=1,
            validation_ready=True,
        ))
    core = (ROOT / CORE).read_text(encoding="utf-8")
    line = method_line(core, "latest_entities")
    calls = timestamp_parses()
    if (line is not None and calls is not None and calls > 8 and
        "utc_datetime(old.observed_at)" in core and
        not (ROOT / CACHE_TEST).exists()):
        opportunities.append(ImprovementOpportunity(
            "cache_latest_entity_timestamps",
            "Avoid reparsing previously selected ERP observation timestamps",
            (f"{CORE}:{line}", f"witness:{calls}_parses_for_8_records"),
            impact=3, reproducibility=5, confidence=1.0, risk=1,
            validation_ready=True,
        ))
    return opportunities


LEDGER_TEST_SOURCE = '''"""Regression against malformed direct Observation instances."""
import unittest

from ezbean.core import Observation
from ezbean.store import Ledger


class DurableLedgerIngressRegression(unittest.TestCase):
    def test_direct_invalid_timestamp_must_fail_before_storage(self):
        ledger = Ledger()
        entry = Observation("erp", "event", "job", "J1", "bad-timestamp",
                            {"due_date": "2026-10-01"})
        with self.assertRaises(ValueError):
            ledger.ingest(entry)
        self.assertEqual(ledger.replay(), [])
        ledger.close()

    def test_direct_blank_identity_must_fail_before_storage(self):
        ledger = Ledger()
        entry = Observation("", "event", "job", "J1",
                            "2026-10-10T00:00:00Z", {})
        with self.assertRaises(ValueError):
            ledger.ingest(entry)
        self.assertEqual(ledger.replay(), [])
        ledger.close()

    def test_direct_bad_payload_rolls_back_full_batch(self):
        ledger = Ledger()
        first = Observation("erp", "valid", "job", "J1",
                            "2026-10-10T00:00:00Z", {"due_date": "2026-10-01"})
        bad = Observation("erp", "invalid", "job", "J2",
                          "2026-10-10T00:00:00Z", ["not", "a", "dict"])
        with self.assertRaises(ValueError):
            ledger.ingest_all([first, bad])
        self.assertEqual(ledger.replay(), [])
        ledger.close()

    def test_valid_observation_still_ingests_and_is_idempotent(self):
        ledger = Ledger()
        entry = Observation("erp", "valid", "job", "J1",
                            "2026-10-10T00:00:00Z", {"due_date": "2026-10-01"})
        self.assertTrue(ledger.ingest(entry))
        self.assertFalse(ledger.ingest(entry))
        self.assertEqual(len(ledger.replay()), 1)
        ledger.close()
'''


CACHE_TEST_SOURCE = '''"""Behavioral equivalence plus an objective, deterministic parse-count metric."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import ezbean.core as core
from ezbean.core import Observation


class TimestampCacheRegression(unittest.TestCase):
    def test_timestamp_parse_once_per_input_and_latest_wins(self):
        events = [
            Observation("erp", str(i), "job", "J1",
                        f"2026-10-01T00:00:{i:02d}+00:00", {})
            for i in range(8)
        ]
        with patch.object(core, "utc_datetime", wraps=core.utc_datetime) as wrapped:
            rows = core.latest_entities(
                list(reversed(events)), datetime(2026, 10, 10, tzinfo=timezone.utc))
            self.assertEqual(wrapped.call_count, len(events))
        self.assertEqual(rows[("erp", "job", "J1")].event_id, "7")

    def test_future_events_are_ignored(self):
        events = [
            Observation("erp", "old", "job", "J1", "2026-10-01T00:00:00Z", {}),
            Observation("erp", "new", "job", "J1", "2026-11-01T00:00:00Z", {}),
        ]
        rows = core.latest_entities(
            events, datetime(2026, 10, 10, tzinfo=timezone.utc))
        self.assertEqual(rows[("erp", "job", "J1")].event_id, "old")
'''


def patch_ledger() -> list[Path]:
    path = ROOT / STORE
    original = path.read_text(encoding="utf-8")
    anchor = "        serialized = json.dumps(observation.payload"
    if original.count(anchor) != 1:
        raise ValueError("ledger source has changed; refuse uncertain edit")
    # Explicit normalization at the only durable write boundary.
    insert = (
        "        observation = Observation.from_dict({\n"
        "            'source': observation.source,\n"
        "            'event_id': observation.event_id,\n"
        "            'entity_type': observation.entity_type,\n"
        "            'entity_id': observation.entity_id,\n"
        "            'observed_at': observation.observed_at,\n"
        "            'payload': observation.payload,\n"
        "        })\n"
    )
    path.write_text(original.replace(anchor, insert + anchor, 1), encoding="utf-8")
    (ROOT / LEDGER_TEST).write_text(LEDGER_TEST_SOURCE, encoding="utf-8")
    return [STORE, LEDGER_TEST]


def patch_cache() -> list[Path]:
    path = ROOT / CORE
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "latest_entities")
    old = ast.get_source_segment(source, node)
    if not old or "utc_datetime(old.observed_at)" not in old:
        raise ValueError("timestamp source changed; refuse uncertain edit")
    replacement = '''def latest_entities(observations: Iterable[Observation], as_of: datetime) -> dict[tuple[str, str, str], Observation]:
    # Cache the parsed timestamp with each candidate. Formerly the incumbent
    # timestamp was reparsed whenever another revision arrived for that entity.
    latest: dict[tuple[str, str, str], tuple[datetime, str, Observation]] = {}
    for o in observations:
        timestamp = utc_datetime(o.observed_at)
        if timestamp > as_of:
            continue
        key = (o.source, o.entity_type, o.entity_id)
        old = latest.get(key)
        if old is None or (timestamp, o.event_id) > (old[0], old[1]):
            latest[key] = (timestamp, o.event_id, o)
    return {key: value[2] for key, value in latest.items()}'''
    if source.count(old) != 1:
        raise ValueError("ambiguous timestamp function; refuse uncertain edit")
    path.write_text(source.replace(old, replacement, 1), encoding="utf-8")
    (ROOT / CACHE_TEST).write_text(CACHE_TEST_SOURCE, encoding="utf-8")
    return [CORE, CACHE_TEST]


def run(*, apply: bool, receipt: Path) -> int:
    baseline = regression()
    report: dict = {
        "project": "BEAN-governed Bridge source improvement",
        "applied": False, "baseline": baseline, "result": "baseline_failed",
        "execution_scope": sorted(str(p) for p in APPROVED_WRITES),
    }
    if not baseline["passed"]:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    candidates = discover()
    ranked = rank_improvements(candidates, max_risk=2)
    report["ranked"] = [
        {"candidate": r.opportunity.identifier, "score": r.score,
         "evidence": list(r.opportunity.evidence_refs)} for r in ranked
    ]
    if not ranked:
        report["result"] = "no_eligible_opportunity"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    selected = ranked[0].opportunity
    report["selected"] = selected.identifier
    report["result"] = "planned_not_executed"
    if not apply:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    policy = {
        "validate_unchecked_ledger_observations": (STORE, patch_ledger, ledger_witness),
        "cache_latest_entity_timestamps": (CORE, patch_cache, timestamp_parses),
    }
    target, action, witness = policy[selected.identifier]
    # This host has only two explicitly implemented, code-reviewed effects.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    governor = SelfOptimizationGovernor(conn)
    proposal = governor.create_proposal(
        session_uuid="bridge_improvement_" + uuid.uuid4().hex,
        title=selected.description,
        problem_statement="Reproducible source defect or waste: " + ", ".join(selected.evidence_refs),
        proposed_change=f"Apply bounded transformation {selected.identifier} to {target}",
        target_layer="software", proposal_type="code_change",
        expected_benefit="Improve a witnessed Bridge invariant or operation count",
        expected_cost="One isolated code change, complete regression suite and reviewable PR",
        risk_level="low",
        evidence_refs=list(selected.evidence_refs),
        validation_plan="Baseline tests pass, independent witness changes in expected direction, full suite passes",
        rollback_plan="Restore original bytes of all approved edited source and tests before exit",
        alternatives=["Retain baseline and report an unresolved candidate"],
        created_by="bean_bridge_ci_host",
    )
    governor.review_proposal(
        proposal["proposal_id"], decision="approve_sandbox",
        reviewer="trusted_ci_host",
        notes="Preauthorized fixed-path local experiment; never auto-merge to main.",
    )
    originals = {
        path: (ROOT / path).read_bytes() if (ROOT / path).exists() else None
        for path in APPROVED_WRITES
    }
    before_witness = witness()
    try:
        changed = action()
        if not set(changed).issubset(APPROVED_WRITES):
            raise RuntimeError("Unauthorized filesystem target")
        result = regression()
        after_witness = witness()
        if selected.identifier == "validate_unchecked_ledger_observations":
            improved = before_witness is True and after_witness is False
        else:
            improved = isinstance(before_witness, int) and isinstance(after_witness, int) and (
                before_witness > after_witness and after_witness == 8
            )
        if not result["passed"] or not improved:
            raise RuntimeError("Independent code or regression acceptance criteria failed")
        governor.mark_outcome(
            proposal["proposal_id"], outcome="validated", reviewer="trusted_ci_host",
            notes="Independent post-edit checks passed; subject to human/CI PR review.",
        )
        report.update({
            "applied": True, "result": "validated_change",
            "changed_paths": [str(p) for p in changed],
            "before_witness": before_witness, "after_witness": after_witness,
            "after": result,
            "proposal_status": governor.get_proposal(proposal["proposal_id"])["status"],
            "before_hash": {str(p): digest(originals[p].decode("utf-8")) for p in changed if originals[p] is not None},
            "after_hash": {str(p): digest((ROOT / p).read_text(encoding="utf-8")) for p in changed},
        })
        return 0
    except Exception as exc:
        for path, old in originals.items():
            absolute = ROOT / path
            if old is None:
                absolute.unlink(missing_ok=True)
            else:
                absolute.write_bytes(old)
        governor.mark_outcome(
            proposal["proposal_id"], outcome="rolled_back", reviewer="trusted_ci_host",
            notes="Validation failed; restored every approved file to original bytes.",
        )
        report["result"] = "rolled_back"
        report["reason"] = type(exc).__name__ + ": " + str(exc)
        return 1
    finally:
        report["proposal_id"] = proposal["proposal_id"]
        report["proposal_status"] = governor.get_proposal(proposal["proposal_id"])["status"]
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                out.write("changed=" + ("true" if report["applied"] else "false") + "\n")
                out.write("candidate=" + report.get("selected", "") + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--apply", action="store_true")
    cli.add_argument("--receipt", type=Path, default=Path(".bean-agent/receipt.json"))
    options = cli.parse_args()
    code = run(apply=options.apply, receipt=options.receipt)
    print(options.receipt.read_text(encoding="utf-8"))
    raise SystemExit(code)
