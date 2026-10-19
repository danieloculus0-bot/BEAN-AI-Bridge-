"""BEAN local 10-workday operational pilot measurement.

This records *only aggregated, manually adjudicated outcomes*, not raw ERP
records or customer/employee identifiers. A SHA256-linked JSONL trial ledger
allows restart/resume and detects accidental alteration of old entries.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
from html import escape
import json
import math
from pathlib import Path

from .daily_brief import SCHEMA as BRIEF_SCHEMA

SCHEMA = "BEAN_OPERATIONAL_PILOT_V1"
TIP = "0" * 64
FIELDS = (
    "day", "site", "brief_sha256", "brief_as_of", "presented_exceptions",
    "baseline_minutes", "bean_minutes", "confirmed_useful", "false_alerts",
    "missed_issues", "previous_sha256",
)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_log(path: Path) -> list[dict]:
    """Replay and validate the complete chain before accepting new evidence."""
    if not path.exists():
        return []
    result = []
    tip = TIP
    seen = set()
    for line_num, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            raise ValueError(f"Blank pilot entry at line {line_num}")
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid pilot JSON at line {line_num}") from exc
        if item.get("schema") != SCHEMA or set(item) != set(FIELDS) | {"schema", "record_sha256"}:
            raise ValueError(f"Invalid pilot record schema at line {line_num}")
        digest = item["record_sha256"]
        original = {k: v for k, v in item.items() if k != "record_sha256"}
        if item["previous_sha256"] != tip or digest != _digest(original):
            raise ValueError(f"Pilot ledger continuity mismatch at line {line_num}")
        key = (item["site"], item["day"])
        if key in seen:
            raise ValueError(f"Duplicate pilot site/day at line {line_num}")
        seen.add(key)
        tip = digest
        result.append(item)
    return result


def _minutes(value: float, field: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 480:
        raise ValueError(field + " must be finite and between 0 and 480 minutes")
    return round(float(value), 2)


def _count(value: int, name: str) -> int:
    if type(value) is not int or value < 0 or value > 100000:
        raise ValueError(name + " must be a nonnegative integer")
    return value


def record(path: Path, brief_path: Path, *, day: str,
           baseline_minutes: float, bean_minutes: float,
           confirmed_useful: int, false_alerts: int, missed_issues: int) -> dict:
    """Append a single human-reviewed day of the pilot, without raw source data."""
    date.fromisoformat(day)
    raw_brief = brief_path.read_bytes()
    brief = json.loads(raw_brief)
    if brief.get("schema") != BRIEF_SCHEMA:
        raise ValueError("Expected BEAN Daily Exception Brief JSON")
    site = brief.get("site")
    if not isinstance(site, str) or not site or len(site) > 32 or not site.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Expected anonymous site code")
    as_of = brief.get("as_of")
    cutoff = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if cutoff.tzinfo is None:
        raise ValueError("Brief cutoff must include a timezone")
    presented = _count(brief.get("open_exception_count"), "open_exception_count")
    useful = _count(confirmed_useful, "confirmed_useful")
    false = _count(false_alerts, "false_alerts")
    misses = _count(missed_issues, "missed_issues")
    if useful + false > presented:
        raise ValueError("Confirmed and false alerts cannot exceed shown exceptions")
    entries = load_log(path)
    if any(entry["site"] == site and entry["day"] == day for entry in entries):
        raise ValueError("Pilot site/day was already recorded; no silent overwrite")
    item = {
        "schema": SCHEMA, "day": day, "site": site,
        "brief_sha256": hashlib.sha256(raw_brief).hexdigest(),
        "brief_as_of": as_of, "presented_exceptions": presented,
        "baseline_minutes": _minutes(baseline_minutes, "baseline_minutes"),
        "bean_minutes": _minutes(bean_minutes, "bean_minutes"),
        "confirmed_useful": useful, "false_alerts": false, "missed_issues": misses,
        "previous_sha256": entries[-1]["record_sha256"] if entries else TIP,
    }
    item["record_sha256"] = _digest(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(_canonical(item).decode("utf-8") + "\n")
    return item


def report(entries: list[dict], *, site: str | None = None) -> dict:
    """Measured outcomes only; no invented customer-demand or readiness score."""
    if site is not None:
        entries = [x for x in entries if x["site"] == site]
    sites = sorted({x["site"] for x in entries})
    days = sorted({(x["site"], x["day"]) for x in entries})
    baseline = round(sum(x["baseline_minutes"] for x in entries), 2)
    bean = round(sum(x["bean_minutes"] for x in entries), 2)
    shown = sum(x["presented_exceptions"] for x in entries)
    useful = sum(x["confirmed_useful"] for x in entries)
    false = sum(x["false_alerts"] for x in entries)
    missed = sum(x["missed_issues"] for x in entries)
    return {
        "schema": "BEAN_OPERATIONAL_PILOT_REPORT_V1", "sites": sites,
        "workdays_recorded": len(days),
        "pilot_complete": bool(len(sites) == 1 and len(days) >= 10),
        "baseline_minutes": baseline, "bean_minutes": bean,
        "minutes_saved": round(baseline - bean, 2),
        "time_reduction_percent": (
            round((baseline - bean) / baseline * 100, 2) if baseline else None
        ),
        "presented_exceptions": shown, "confirmed_useful": useful,
        "false_alerts": false, "missed_issues": missed,
        "confirmed_share_of_all_presented_percent": (
            round(100 * useful / shown, 2) if shown else None
        ),
        "entries_per_site": {
            s: sum(x["site"] == s for x in entries) for s in sites
        },
        "limitations": [
            "Reviewer-adjudicated aggregate measurements, not independent ground truth.",
            "Compare identical daily source snapshots and equal review scope in both arms.",
            "Pilot coverage does not prove demand, paid conversion or enterprise deployment.",
            "No customer, employee, source row, job or RMA identifiers are recorded.",
            "The record hash chain detects edited historical entries, not malicious replacement of the entire file.",
        ],
    }


def render_html(result: dict) -> str:
    esc = lambda x: escape(str(x), quote=True)
    rows = [
        ("Workdays recorded", result["workdays_recorded"]),
        ("Ten-workday single-site trial complete", result["pilot_complete"]),
        ("Manual baseline minutes", result["baseline_minutes"]),
        ("BEAN-assisted minutes", result["bean_minutes"]),
        ("Net minutes saved", result["minutes_saved"]),
        ("Time reduction percent", result["time_reduction_percent"]),
        ("Exceptions presented", result["presented_exceptions"]),
        ("Confirmed useful exceptions", result["confirmed_useful"]),
        ("False alerts", result["false_alerts"]),
        ("Issues missed in BEAN-assisted review", result["missed_issues"]),
        ("Confirmed share of all presented, %", result["confirmed_share_of_all_presented_percent"]),
    ]
    cells = "".join(
        "<tr><td>" + esc(name) + "</td><td>" + esc(value if value is not None else "N/A") + "</td></tr>"
        for name, value in rows
    )
    limits = "".join("<li>" + esc(note) + "</li>" for note in result["limitations"])
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>BEAN Pilot Evidence</title>'
        '<style>body{font-family:system-ui;max-width:840px;margin:auto;padding:28px}'
        'table{width:100%;border-collapse:collapse}td{padding:10px;border-bottom:1px solid #ddd}'
        'h1{color:#285d31}</style>'
        '<h1>BEAN — Operational Pilot Evidence</h1><p>Local, anonymous and reviewer-adjudicated.</p>'
        '<table>' + cells + '</table><h2>Limitations</h2><ul>' + limits + '</ul></html>'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure a private ten-workday BEAN operational pilot")
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("record", help="Append one observed workday")
    write.add_argument("--log", required=True, type=Path)
    write.add_argument("--brief", required=True, type=Path)
    write.add_argument("--day", required=True)
    write.add_argument("--baseline-minutes", required=True, type=float)
    write.add_argument("--bean-minutes", required=True, type=float)
    write.add_argument("--confirmed-useful", required=True, type=int)
    write.add_argument("--false-alerts", required=True, type=int)
    write.add_argument("--missed-issues", required=True, type=int)
    view = sub.add_parser("report", help="Validate ledger and show outcomes")
    view.add_argument("--log", required=True, type=Path)
    view.add_argument("--site")
    view.add_argument("--out", type=Path, help="Optional private HTML report; also writes JSON")
    args = parser.parse_args()
    if args.command == "record":
        saved = record(
            args.log, args.brief, day=args.day,
            baseline_minutes=args.baseline_minutes, bean_minutes=args.bean_minutes,
            confirmed_useful=args.confirmed_useful, false_alerts=args.false_alerts,
            missed_issues=args.missed_issues,
        )
        print(json.dumps({"day": saved["day"], "site": saved["site"],
                          "record_sha256": saved["record_sha256"]}))
    else:
        result = report(load_log(args.log), site=args.site)
        if args.out:
            if args.out.suffix.lower() != ".html":
                parser.error("--out must use .html")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(render_html(result), encoding="utf-8")
            args.out.with_suffix(".json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
