"""BEAN Bridge: evidence-first discovery of reporting metamorphic violations.

Searches synthetic ERP inputs for invariants which must hold independent of
record order or timezone representation. The hunter writes reproducible
witnesses; it NEVER patches source, guesses root cause, publishes ERP data,
or claims that a finding is fixed. Intended to feed peer engineering reviews.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
from typing import Callable

from ezbean.core import Observation, calculate

SCHEMA = "bean.bridge.metamorphic.v1"
DOMAINS = ("job", "rma", "production")
OFFSETS = (-12, -10, -8, -5, -3, 0, 3, 5, 8, 9, 12, 14)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def obs(kind, ident, observed_at, payload):
    return Observation("synthetic_meta_erp", ident, kind, ident,
                       observed_at, payload)


def build_fixture(domain: str, cutoff: datetime):
    """Construct a coverage-asserted, time-bound synthetic entity."""
    if domain not in DOMAINS:
        raise ValueError("unsupported synthetic domain")
    cutoff = cutoff.astimezone(timezone.utc)
    day = cutoff.date().isoformat()
    start = cutoff.date().replace(day=1).isoformat()
    earlier = (cutoff - timedelta(minutes=10)).isoformat()
    if domain == "job":
        fact = {"due_date": day, "shipped_date": day}
    elif domain == "rma":
        fact = {"opened_date": day, "quantity": 1, "cost": "37.50"}
    else:
        fact = {"production_date": day, "good_units": 90, "scrap_units": 10}
    claim = {
        "domain": domain,
        "window_start": start,
        "through": cutoff.isoformat(),
        "scope": "full_snapshot" if domain == "job" else "reporting_window",
        "complete": True,
    }
    return start, [
        obs(domain, "synthetic-fact", earlier, fact),
        obs("source_coverage", "synthetic-coverage", earlier, claim),
    ]


def projection(report):
    """Ignore the caller's equivalent *textual* as-of value, not the facts."""
    obj = report.to_dict()
    return {"kpis": obj["kpis"], "coverage": obj["source_coverage"],
            "input_count": obj["input_count"]}


def display_fixture(rows):
    return [asdict(row) for row in rows]


def compare_one(rows, start, cutoff, alternative, *, calculator=None):
    """Return a machine-verifiable comparison without assuming a repair."""
    calculator = calculator or calculate
    baseline = calculator(rows, start, cutoff)
    alternate = calculator(rows, start, alternative)
    a = projection(baseline)
    b = projection(alternate)
    return {"equal": a == b, "baseline": a, "alternate": b,
            "changed_kpis": sorted(key for key in a["kpis"]
                                   if a["kpis"][key] != b["kpis"][key]),
            "changed_coverage": sorted(key for key in a["coverage"]
                                       if a["coverage"][key] != b["coverage"][key])}


def run(*, seed: int = 20261010, trials: int = 60):
    if not 1 <= trials <= 2000:
        raise ValueError("trial budget must be 1..2000")
    rng = random.Random(seed)
    findings = []
    invariant_checks = 0
    for index in range(trials):
        domain = DOMAINS[index % len(DOMAINS)]
        # Challenge dates both near and far from midnight so a reporting
        # policy error cannot hide inside only convenient daytime fixtures.
        offset_minute = rng.choice((10, 30, 55, 12 * 60 + 5, 22 * 60 + 30, 23 * 60 + 45))
        day = 1 + rng.randrange(1, 27)
        cutoff_dt = (datetime(2026, 10, day, tzinfo=timezone.utc)
                     + timedelta(minutes=offset_minute))
        utc = cutoff_dt.isoformat()
        zone_hours = OFFSETS[index % len(OFFSETS)]
        alternate = cutoff_dt.astimezone(timezone(timedelta(hours=zone_hours))).isoformat()
        start, records = build_fixture(domain, cutoff_dt)
        baseline = compare_one(records, start, utc, alternate)
        invariant_checks += 1
        if not baseline["equal"]:
            findings.append({
                "test_case": index,
                "invariant": "equivalent_cutoff_instants_preserve_kpi_evidence",
                "domain": domain,
                "cutoff_utc": utc,
                "same_instant_in_offset": alternate,
                "calendar_policy": "generic UTC comparator; site-local policy not asserted",
                "changed_kpis": baseline["changed_kpis"],
                "changed_coverage": baseline["changed_coverage"],
                "source_coverage_asserted": (
                    baseline["baseline"]["coverage"][domain]["state"] == "ASSERTED_COMPLETE"
                    and baseline["alternate"]["coverage"][domain]["state"] == "ASSERTED_COMPLETE"
                ),
                "baseline_values": {k: baseline["baseline"]["kpis"][k]["value"]
                                    for k in baseline["changed_kpis"]},
                "alternate_values": {k: baseline["alternate"]["kpis"][k]["value"]
                                     for k in baseline["changed_kpis"]},
                "synthetic_rows": display_fixture(records),
            })
        shuffled = list(records)
        rng.shuffle(shuffled)
        reordered = compare_one(shuffled, start, utc, utc)
        invariant_checks += 1
        if not reordered["equal"] or projection(calculate(records, start, utc)) != projection(calculate(shuffled, start, utc)):
            findings.append({
                "test_case": index, "invariant": "input_reordering_preserves_report",
                "domain": domain, "cutoff_utc": utc,
                "synthetic_rows": display_fixture(records),
            })
        # Data timestamps are absolute instants too; re-encoding each event
        # must not change event eligibility or selection.
        transcoded = [
            Observation(row.source, row.event_id, row.entity_type, row.entity_id,
                        datetime.fromisoformat(row.observed_at).astimezone(
                            timezone(timedelta(hours=zone_hours))).isoformat(),
                        row.payload)
            for row in records
        ]
        invariant_checks += 1
        if projection(calculate(records, start, utc)) != projection(calculate(transcoded, start, utc)):
            findings.append({
                "test_case": index, "invariant": "equivalent_observation_instants_preserve_report",
                "domain": domain, "cutoff_utc": utc,
                "synthetic_rows": display_fixture(records),
            })
    unique = {}
    for row in findings:
        key = row["invariant"] + "/" + row["domain"] + "/" + str(
            tuple(row.get("changed_kpis", [])))
        unique.setdefault(key, row)
    results = {
        "schema": SCHEMA, "seed": seed, "trials": trials,
        "invariant_checks": invariant_checks,
        "finding_occurrences": len(findings),
        "distinct_finding_families": len(unique),
        "status": "FINDINGS_REQUIRE_PEER_REVIEW" if findings else "NO_VIOLATION_OBSERVED",
        "synthetic_only": True,
        "findings": list(unique.values()),
    }
    results["receipt_sha256"] = digest(results)
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=20261010)
    p.add_argument("--trials", type=int, default=60)
    p.add_argument("--receipt", type=Path, default=Path(".bean-hunter/evidence.json"))
    p.add_argument("--fail-on-finding", action="store_true")
    args = p.parse_args()
    report = run(seed=args.seed, trials=args.trials)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "findings"},
                     indent=2, sort_keys=True))
    return 1 if args.fail_on_finding and report["finding_occurrences"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
