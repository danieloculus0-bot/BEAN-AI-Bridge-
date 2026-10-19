"""BEAN Daily Exception Brief: private, read-only, export-snapshot review.

This module uses the already normalized management intelligence layer and never
returns raw JobBOSS rows, customer IDs, employee names, paths, or row references.
Verification status refers to documented local source checks, not independent
authentication of the exporting ERP. It does not send notifications or make ERP
changes.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from html import escape
import json
import math
from pathlib import Path
from typing import Any

from .jobboss_exports import ExportSponge
from .management_intelligence import analyze_site

SCHEMA = "BEAN_DAILY_EXCEPTION_BRIEF_V1"

# Explicit allowlist. These are local source-derived indicators, not customer
# scorecard metrics or audited production truth.
DISPLAY_METRICS = (
    ("shipment_line_otd", "Shipment-line OTD"),
    ("shipment_lines", "Shipped report lines"),
    ("on_time_shipment_lines", "On-time shipped lines"),
    ("past_due_open_job_lines", "Past-due open job lines"),
    ("rma_observed", "Dated RMA occurrences"),
    ("rma_quantity", "RMA quantity"),
    ("rma_cost", "RMA cost"),
)
GAP_GUIDANCE = {
    "SHIPMENT_EXPORT_MISSING": ("P0", "Export Shipment Summary before interpreting OTD."),
    "SHIPMENT_LINES_EMPTY": ("P1", "Review shipment window and source coverage; OTD is N/A."),
    "SHIPMENT_DATE_CONFLICT": ("P0", "Reconcile shipped/due dates and DaysEarlyLate against the original export."),
    "SHIPMENT_DATE_UNVERIFIED": ("P1", "Verify missing DaysEarlyLate checks; avoid publishing source-unverified OTD."),
    "SCHEDULE_EXPORT_MISSING": ("P0", "Provide a Job Schedule export for open-job status."),
    "SCHEDULE_SHIP_STATUS_UNKNOWN": ("P0", "Verify missing shipped quantity on due-date lines before classifying overdue jobs."),
    "RMA_EXPORT_MISSING": ("P0", "Provide an RMA Tracker export; unknown RMA count is not zero."),
    "RMA_DATE_QUARANTINE": ("P0", "Reconcile quarantined RMA dates with the original source; observed count is a lower bound."),
    "RMA_QUANTITY_UNKNOWN": ("P2", "RMA units require a separately validated source column."),
    "RMA_COST_UNKNOWN": ("P2", "RMA cost requires a separately validated cost source."),
    "OTD_POLICY_UNCONFIRMED": ("P1", "Obtain approval for the official customer OTD policy before using this as a scorecard."),
}
PRIORITY = {"P0": 0, "P1": 1, "P2": 2}


def _instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("As-of timestamp must be a timezone-aware ISO-8601 string")
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO-8601 as-of timestamp") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise ValueError("As-of timestamp must include a timezone")
    return out.astimezone(timezone.utc)


def _site(summary: dict[str, Any]) -> tuple[str, date, datetime]:
    if not isinstance(summary, dict) or summary.get("schema") != "BEAN_MANAGEMENT_INTELLIGENCE_V1":
        raise ValueError("Expected a sanitized BEAN management intelligence summary")
    site = summary.get("site")
    if not isinstance(site, str) or not site or len(site) > 32 or not site.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Invalid anonymous site code")
    try:
        window = date.fromisoformat(summary["window_start"])
        cutoff = _instant(summary["as_of"])
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("Invalid reporting window or cutoff") from exc
    if window > cutoff.date():
        raise ValueError("Reporting window starts after cutoff")
    if not isinstance(summary.get("metrics"), dict) or not isinstance(summary.get("gaps"), list):
        raise ValueError("Invalid summary metrics or gap list")
    return site, window, cutoff


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _display_metric(metric: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    state = metric.get("state")
    if state not in ("VERIFIED", "UNKNOWN", "CONFLICTED", "CORRECTED"):
        raise ValueError("Invalid metric evidence state")
    value = metric.get("value")
    if value is not None and not _number(value):
        raise ValueError("Invalid metric value")
    is_checked = state in ("VERIFIED", "CORRECTED")
    # When invalid RMA dates are quarantined, a numeric occurrence count is a
    # minimum observed count, NOT a proven total.
    lower = value if key == "rma_observed" and state == "UNKNOWN" else None
    return {
        "label": label,
        "value": value if is_checked else None,
        "observed_lower_bound": lower,
        "unit": str(metric.get("unit", ""))[:16] if is_checked else "",
        "evidence_state": state,
        "interpretation": ("Source-reconciled local export measure; policy may still be unapproved."
                           if is_checked else "Not established from available source evidence."),
    }


def _gap_codes(summary: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for gap in summary["gaps"]:
        if not isinstance(gap, dict) or not isinstance(gap.get("code"), str):
            raise ValueError("Invalid gap record")
        # Never include source-originated prose, names or free-form details.
        if gap["code"] in GAP_GUIDANCE:
            result.add(gap["code"])
    return result


def build_daily_brief(current: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a sanitized, deterministic, decision-ready exception snapshot."""
    site, window, cutoff = _site(current)
    if previous is not None:
        prior_site, prior_window, prior_cutoff = _site(previous)
        if (site, window) != (prior_site, prior_window):
            raise ValueError("Previous summary must use the same site and reporting start")
        if prior_cutoff >= cutoff:
            raise ValueError("Previous summary must be from an earlier cutoff")
    else:
        prior_cutoff = None

    metrics = {}
    changes = []
    for key, label in DISPLAY_METRICS:
        item = current["metrics"].get(key, {"value": None, "state": "UNKNOWN"})
        if not isinstance(item, dict):
            raise ValueError("Invalid metric structure")
        m = _display_metric(item, key, label)
        metrics[key] = m
        if previous is not None:
            before = previous["metrics"].get(key, {"value": None, "state": "UNKNOWN"})
            if not isinstance(before, dict):
                raise ValueError("Invalid prior metric structure")
            old = _display_metric(before, key, label)
            if m["value"] is not None and old["value"] is not None and m["unit"] == old["unit"]:
                changes.append({
                    "metric": key,
                    "from": old["value"],
                    "to": m["value"],
                    "delta": round(m["value"] - old["value"], 4),
                    "interpretation": "Difference between source-checked snapshots, not evidence of cause or improved performance.",
                })

    current_gaps = _gap_codes(current)
    prior_gaps = _gap_codes(previous) if previous is not None else set()
    new_gaps = sorted(current_gaps - prior_gaps) if previous is not None else []
    resolved = sorted(prior_gaps - current_gaps) if previous is not None else []
    queue = sorted(current_gaps, key=lambda code: (PRIORITY[GAP_GUIDANCE[code][0]], code))
    actions = [
        {"code": code, "priority": GAP_GUIDANCE[code][0],
         "next_check": GAP_GUIDANCE[code][1],
         "since_previous": "new" if code in new_gaps else "existing" if previous else "uncompared"}
        for code in queue
    ]
    return {
        "schema": SCHEMA,
        "mode": "LOCAL_PRIVATE_READ_ONLY",
        "site": site,
        "window_start": window.isoformat(),
        "as_of": cutoff.isoformat(),
        "previous_as_of": prior_cutoff.isoformat() if prior_cutoff else None,
        "comparison": ("SAME_PERIOD_DIFFERENT_CUTOFF_SNAPSHOTS"
                       if prior_cutoff else "NO_PREVIOUS_SNAPSHOT"),
        "metrics": metrics,
        "snapshot_deltas": changes,
        "open_exception_count": len(actions),
        "exceptions": actions,
        "new_gap_codes": new_gaps,
        "resolved_gap_codes": resolved,
        "limitations": [
            "The source snapshots were exported by a host; BEAN did not authenticate the ERP.",
            "Shipment-line OTD is not an approved customer scorecard or an order-level delivery measure.",
            "Snapshot deltas may reflect corrected files, late exports, or different cutoffs; they are not causal trends.",
            "A missing/unreconciled number remains N/A; an RMA lower bound is not the total.",
            "This local summary omits raw customer, job, employee and order identifiers.",
            "No root cause, release approval, action owner, automated email or ERP write is produced.",
        ],
    }


def render_html(brief: dict[str, Any]) -> str:
    """Static offline HTML; values and labels are escaped, without external assets."""
    if brief.get("schema") != SCHEMA:
        raise ValueError("Unsupported brief schema")
    e = lambda x: escape(str(x), quote=True)
    rows = []
    for key, _ in DISPLAY_METRICS:
        metric = brief["metrics"][key]
        value = metric["value"]
        if value is None:
            lower = metric["observed_lower_bound"]
            shown = ("N/A (at least " + str(lower) + " observed)" if lower is not None else "N/A")
        else:
            shown = str(value) + ("%" if metric["unit"] == "%" else "")
        rows.append("<tr><td>" + e(metric["label"]) + "</td><td><strong>" +
                    e(shown) + "</strong></td><td>" + e(metric["evidence_state"]) + "</td></tr>")
    gaps = "".join("<li><strong>" + e(x["priority"]) + " " + e(x["code"]) +
                   "</strong>: " + e(x["next_check"]) + "</li>" for x in brief["exceptions"])
    gaps = gaps or "<li>No gaps detected by this adapter; source completeness still requires review.</li>"
    delta = "".join("<li>" + e(brief["metrics"][x["metric"]]["label"]) + ": " +
                    e(x["from"]) + " → " + e(x["to"]) + " (" +
                    e(f'{x["delta"]:+g}') + " unit difference)</li>" for x in brief["snapshot_deltas"])
    delta = delta or "<li>No comparable source-checked values across both snapshots.</li>"
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BEAN | Daily Exception Brief</title><style>
:root{font-family:system-ui,Arial,sans-serif;background:#f7fbf4;color:#182b1c}
body{max-width:940px;margin:auto;padding:24px}
header,section{border:1px solid #d6e8d2;border-radius:16px;background:white;padding:24px;margin:14px 0;
box-shadow:0 8px 22px #254e2912}
h1{margin:0}h2{color:#24682d}small,.note{color:#4e6150}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #e4eee2}
ul{line-height:1.7}strong{color:#215a27}
</style></head><body><header><h1>🌱 BEAN Daily Exception Brief</h1><p>PRIVATE · LOCAL · READ ONLY</p>
<p>Site """ + e(brief["site"]) + " · " + e(brief["window_start"]) + " through " +
            e(brief["as_of"]) + """</p></header><section><h2>Evidence status</h2>
<table><thead><tr><th>Metric</th><th>Value</th><th>State</th></tr></thead><tbody>""" +
            "".join(rows) + """</tbody></table></section>
<section><h2>Review queue</h2><ol>""" + gaps + """</ol></section>
<section><h2>Snapshot changes</h2><ul>""" + delta + """</ul>
<p class="note">These differences are between earlier and later source snapshots for the same reporting start.
They are not proof of operational improvement or newly created records.</p></section>
<section><h2>Important limits</h2><ul>""" +
            "".join("<li>" + e(x) + "</li>" for x in brief["limitations"]) +
            """</ul></section></body></html>""")


def main() -> None:
    parser = argparse.ArgumentParser(description="Private local BEAN daily exception brief")
    parser.add_argument("--database", type=Path, required=True, help="Existing private JobBOSS export SQLite ledger")
    parser.add_argument("--site", default="SITE_A", help="Anonymous site code")
    parser.add_argument("--start", required=True, help="Reporting period start YYYY-MM-DD")
    parser.add_argument("--as-of", required=True, help="Timezone-aware current source cutoff")
    parser.add_argument("--previous-as-of", help="Earlier source cutoff for same period")
    parser.add_argument("--out", required=True, type=Path, help="Local HTML path; JSON saved beside it")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Existing local export SQLite ledger required")
    if args.out.suffix.lower() != ".html":
        parser.error("--out must use an .html filename")
    if args.previous_as_of and _instant(args.previous_as_of) >= _instant(args.as_of):
        parser.error("--previous-as-of must precede --as-of")
    sponge = ExportSponge(args.database)
    try:
        current = analyze_site(args.site, sponge.report(args.start, args.as_of))
        previous = (analyze_site(args.site, sponge.report(args.start, args.previous_as_of))
                    if args.previous_as_of else None)
        brief = build_daily_brief(current, previous)
    finally:
        sponge.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(brief), encoding="utf-8")
    args.out.with_suffix(".json").write_text(json.dumps(brief, indent=2, sort_keys=True) + "\n",
                                             encoding="utf-8")
    print(json.dumps({"status": "LOCAL_PRIVATE_READ_ONLY", "html": str(args.out),
                      "json": str(args.out.with_suffix(".json")),
                      "open_exceptions": brief["open_exception_count"],
                      "comparable_snapshot_metrics": len(brief["snapshot_deltas"])}))


if __name__ == "__main__":
    main()
