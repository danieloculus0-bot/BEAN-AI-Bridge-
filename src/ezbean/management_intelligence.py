"""Privacy-minimized BEAN management intelligence over JobBOSS export summaries.

This is deterministic, evidence-constrained reasoning: not neural model inference.
Raw customer, employee, order, and job identifiers never enter this output API.
The local SQLite ledgers retain source rows for authorized audit/replay.
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jobboss_exports import ExportSponge

_ALLOWED_METRICS = {
    "otd_percent_by_shipment_line", "shipment_lines", "on_time_shipment_lines",
    "partially_shipped_lines", "past_due_open_job_lines", "schedule_due_date_lines",
    "schedule_missing_shipped_quantity_lines", "rma_entries",
    "rma_missing_reason_entries", "rma_quantity", "rma_cost_usd",
}
_STATUSES = {"VERIFIED", "UNKNOWN", "CONFLICTED", "CORRECTED"}
_COLORS = {"VERIFIED":"#166534","UNKNOWN":"#9a6700","CONFLICTED":"#9f1239",
           "CORRECTED":"#1d4ed8"}


def _metric(value: Any, unit: str, state: str, explanation: str) -> dict:
    if state not in _STATUSES:
        raise ValueError("Invalid evidence state")
    return {"value":value,"unit":unit,"state":state,"explanation":explanation}


def _gap(code: str, message: str, severity: str="data_quality") -> dict:
    return {"code":code,"severity":severity,"question":message}


def analyze_site(site: str, report: dict) -> dict:
    """Convert bridge output into a strictly non-identifying management summary."""
    if not isinstance(site,str) or not (1<=len(site)<=32) or not site.replace("-","").replace("_","").isalnum():
        raise ValueError("Site must be a short non-identifying code")
    if report.get("schema")!="BEAN_JOBBOSS_EXPORT_V1":
        raise ValueError("Unsupported bridge export schema")
    raw=report["metrics"]
    v=report.get("source_verification",{}).get("shipment_days_early_late",{})
    gaps=[]
    if raw.get("shipment_lines") is None:
        gaps.append(_gap("SHIPMENT_EXPORT_MISSING",
                         "Provide a Shipment Summary export for this reporting period."))
    elif not raw["shipment_lines"]:
        gaps.append(_gap("SHIPMENT_LINES_EMPTY",
                         "No shipping lines meet this report window; OTD is not determinable."))
    if v.get("status")=="conflicted":
        gaps.append(_gap("SHIPMENT_DATE_CONFLICT",
                         "JobBOSS DaysEarlyLate disagrees with shipped-minus-due dates; reconcile the report."))
    elif v.get("status")!="verified":
        gaps.append(_gap("SHIPMENT_DATE_UNVERIFIED",
                         "Provide or reconcile JobBOSS DaysEarlyLate for every included shipped line."))
    otd=raw.get("otd_percent_by_shipment_line")
    if otd is None:
        otd_state="UNKNOWN"
    elif v.get("status")=="verified" and v.get("reconciled_lines")==raw.get("shipment_lines"):
        otd_state="VERIFIED"
    elif v.get("status")=="conflicted":
        otd_state="CONFLICTED"
    else:
        otd_state="UNKNOWN"
    if raw.get("schedule_due_date_lines") is None:
        gaps.append(_gap("SCHEDULE_EXPORT_MISSING","Provide a Job Schedule export."))
    elif raw.get("schedule_missing_shipped_quantity_lines",0)>0:
        gaps.append(_gap("SCHEDULE_SHIP_STATUS_UNKNOWN",
                         "Job Schedule lacks shipped quantity on due-date lines. Do not classify them as open."))
    if raw.get("rma_entries") is None:
        gaps.append(_gap("RMA_EXPORT_MISSING","Provide the RMA Tracker workbook."))
    quarantine=len(report.get("quarantined_rma_rows",[]))
    if quarantine:
        gaps.append(_gap("RMA_DATE_QUARANTINE",
                         "Reconcile invalid RMA dates by checking the original record; do not guess."))
    if raw.get("rma_missing_reason_entries",0):
        gaps.append(_gap("RMA_REASON_MISSING",
                         "Some RMA occurrences lack classification. Verify their reason codes."))
    if raw.get("rma_quantity") is None:
        gaps.append(_gap("RMA_QUANTITY_UNKNOWN",
                         "Provide a validated source for returned quantities."))
    if raw.get("rma_cost_usd") is None:
        gaps.append(_gap("RMA_COST_UNKNOWN",
                         "Provide a validated source for RMA costs."))
    # This exact formula is shipment-line OTD, NOT an official customer scorecard.
    gaps.append(_gap("OTD_POLICY_UNCONFIRMED",
                     "Confirm official shipment-line/partial-shipment promise-date policy before labeling this customer OTD."))
    metrics={
        "shipment_line_otd":_metric(otd,"%",otd_state,
            "Shipped-on-or-before-due / shipped report lines; JobBOSS days check "+v.get("status","unavailable")),
        "shipment_lines":_metric(raw.get("shipment_lines"),"lines",
            "VERIFIED" if raw.get("shipment_lines") is not None else "UNKNOWN",
            "Dated shipment rows within period"),
        "on_time_shipment_lines":_metric(raw.get("on_time_shipment_lines"),"lines",otd_state,
            "Shipment dates compared with due dates"),
        "partially_shipped_lines":_metric(raw.get("partially_shipped_lines"),"lines",
            "VERIFIED" if raw.get("partially_shipped_lines") is not None else "UNKNOWN",
            "Shipped quantity is less than ordered quantity in a shipment record"),
        "past_due_open_job_lines":_metric(raw.get("past_due_open_job_lines"),"lines",
            "VERIFIED" if raw.get("past_due_open_job_lines") is not None else "UNKNOWN",
            "Unavailable if due-date job rows do not contain shipped quantity"),
        "schedule_due_date_lines":_metric(raw.get("schedule_due_date_lines"),"lines",
            "VERIFIED" if raw.get("schedule_due_date_lines") is not None else "UNKNOWN",
            "Scheduled due-date rows, not a proven open-job total"),
        "rma_observed":_metric(raw.get("rma_entries"),"valid dated rows",
            ("UNKNOWN" if quarantine or raw.get("rma_entries") is None else "VERIFIED"),
            ("At least this many valid dated occurrences; total not proven" if quarantine
             else "Dated RMA Log occurrences; not necessarily unique return authorizations")),
        "rma_quantity":_metric(raw.get("rma_quantity"),"units",
            "UNKNOWN" if raw.get("rma_quantity") is None else "VERIFIED","Requires a validated quantity column"),
        "rma_cost":_metric(raw.get("rma_cost_usd"),"USD",
            "UNKNOWN" if raw.get("rma_cost_usd") is None else "VERIFIED","Requires validated RMA cost source"),
    }
    # Never copy raw evidence, reason code text, source filenames, paths, identifiers,
    # descriptions or free-form comments into the anonymous public-facing summary.
    return {
        "site":site,"window_start":report["window_start"],"as_of":report["as_of"],
        "schema":"BEAN_MANAGEMENT_INTELLIGENCE_V1",
        "metrics":metrics,
        "gaps":sorted(gaps,key=lambda x:x["code"]),
        "data_quality_counts":{
            "quarantined_rma_rows":quarantine,
            "missing_rma_reason_entries":raw.get("rma_missing_reason_entries"),
            "missing_schedule_shipping_status":raw.get("schedule_missing_shipped_quantity_lines"),
            "shipment_day_conflicts":v.get("conflicting_lines"),
            "shipment_day_checks":v.get("reconciled_lines"),
        },
    }


def compare_sites(primary: dict, peer: dict|None=None, previous: dict|None=None) -> dict:
    """Comparison is suppressed unless dates, definitions, and evidence all match."""
    if peer is None:
        comparison={"state":"UNKNOWN","ranking":None,"difference_points":None,
                    "reason":"Peer-site data not available. No comparison or winner can be claimed."}
    elif primary["window_start"]!=peer["window_start"] or primary["as_of"]!=peer["as_of"]:
        comparison={"state":"UNKNOWN","ranking":None,"difference_points":None,
                    "reason":"Reporting windows or cutoffs do not match."}
    else:
        pm=primary["metrics"]["shipment_line_otd"]
        wm=peer["metrics"]["shipment_line_otd"]
        if pm["state"]!="VERIFIED" or wm["state"]!="VERIFIED":
            comparison={"state":"UNKNOWN","ranking":None,"difference_points":None,
                        "reason":"One or both shipment-line OTD values are not verified."}
        elif not (0<=pm["value"]<=100 and 0<=wm["value"]<=100):
            comparison={"state":"CONFLICTED","ranking":None,"difference_points":None,
                        "reason":"One or both OTD values are outside valid range."}
        else:
            delta=round(pm["value"]-wm["value"],2)
            comparison={"state":"VERIFIED","ranking":("primary_higher" if delta>0 else
                        "peer_higher" if delta<0 else "tie"),"difference_points":delta,
                        "reason":"Both shipment-line OTD checks verified for the same reporting period; no site-wide superiority implied."}
    gaps=primary["gaps"][:]
    if comparison["state"]!="VERIFIED":
        gaps.append(_gap("PEER_COMPARISON_NOT_VERIFIED",
                         comparison["reason"],"comparison"))
    if previous is not None:
        if previous.get("site")!=primary["site"] or previous.get("window_start")!=primary["window_start"]:
            raise ValueError("Previous comparison must use same site and window")
        old_gaps={z["code"] for z in previous.get("gaps",[])}
        new_gaps={z["code"] for z in gaps}
        resolved=sorted(old_gaps-new_gaps)
        changes=[]
        for key,metric in primary["metrics"].items():
            before=previous.get("metrics",{}).get(key,{})
            if before.get("state") in ("UNKNOWN","CONFLICTED") and metric["state"]=="VERIFIED":
                metric["state"]="CORRECTED"
                changes.append(key)
    else:
        resolved=[]
        changes=[]
    return {
        "schema":"BEAN_EXECUTIVE_BRIDGE_V1",
        "mode":"ANONYMOUS_AGGREGATE_READ_ONLY",
        "primary":primary,
        "peer":peer,
        "comparison":comparison,
        "gaps":sorted(gaps,key=lambda x:x["code"]),
        "resolved_gaps":resolved,
        "corrected_metrics":changes,
        "provenance":"Local source snapshots remain in private SQLite; this summary intentionally excludes row-level evidence and identifiers.",
        "publication":"PRIVATE - explicit review required before redistribution",
    }


def render_html(output:dict,management_note:str="")->str:
    """Offline HTML; no scripts, images, network requests, or raw evidence."""
    esc=lambda x:html.escape(str(x),quote=True)
    p=output["primary"]
    peer=output["peer"]
    def card(site,heading):
        if not site:
            return '<section class="tile"><h2>'+heading+'</h2><p>Not available — no export data</p></section>'
        elems=['<section class="tile"><h2>'+heading+'</h2>']
        for key,label in (("shipment_line_otd","Shipment-line OTD"),("shipment_lines","Shipment lines"),
                          ("past_due_open_job_lines","Verified past due open lines"),
                          ("rma_observed","RMA dated occurrences"),("rma_quantity","RMA quantity"),
                          ("rma_cost","RMA cost (USD)")):
            m=site["metrics"][key]
            val="N/A" if m["value"] is None else str(m["value"])+(" %" if m["unit"]=="%" else "")
            elems.append('<div class="metric"><span>'+esc(label)+'</span><strong>'+esc(val)+'</strong>'+
                         '<span class="state '+m["state"].lower()+'">'+esc(m["state"])+'</span></div>')
        elems.append('</section>')
        return "\n".join(elems)
    gap_html="\n".join('<li><strong>'+esc(g["code"])+'</strong>: '+esc(g["question"])+'</li>'
                       for g in output["gaps"]) or "<li>None</li>"
    note=('<section class="note"><h2>Private management note</h2><p>'+esc(management_note)+'</p></section>'
          if management_note else "")
    comp=output["comparison"]
    comp_text=(f'{comp["difference_points"]:+.2f} percentage points (primary minus peer)'
               if comp["state"]=="VERIFIED" else "N/A")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BEAN | Executive Evidence Report</title>
<style>
:root{{font-family:system-ui,Arial,sans-serif;color:#f8fafc;background:#08172a}}
body{{max-width:1100px;margin:auto;padding:24px}}
h1{{font-size:2rem;margin-bottom:0}}.subtitle{{color:#a9b8cd;margin-top:6px}}
.layout{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}
.tile,.note,.comparison,.gaps{{border:1px solid #294263;background:#11253e;border-radius:12px;padding:18px;margin-top:14px}}
.metric{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 0;border-bottom:1px solid #2a415e}}
.metric span:first-child{{flex:1}}.metric strong{{font-size:1.15rem;white-space:nowrap}}
.state{{font-size:.7rem;padding:4px 7px;border-radius:12px;border:1px solid #51647c}}
.verified{{color:#86efac}}.unknown{{color:#fde68a}}.conflicted{{color:#fda4af}}.corrected{{color:#93c5fd}}
ul{{line-height:1.7}}footer{{font-size:.78rem;color:#a9b8cd;margin-top:25px}}
</style></head><body>
<h1>BEAN | Executive Evidence Report</h1>
<p class="subtitle">Private · {esc(p["window_start"])} through {esc(p["as_of"])} · Aggregate-only reporting</p>
<div class="layout">{card(p,esc(p["site"]))}{card(peer,esc(peer["site"]) if peer else "Peer Site")}</div>
<section class="comparison"><h2>Comparable performance</h2><p><strong>{esc(comp_text)}</strong> — {esc(comp["state"])}</p>
<p>{esc(comp["reason"])}</p></section>
<section class="gaps"><h2>BEAN gap-resolution queue</h2><ul>{gap_html}</ul></section>
{note}
<footer>Local-only export. This document contains no raw ERP rows or personal identifiers.
Source evidence and correction history remain in the private BEAN ledger. No email or publishing action is performed.</footer>
</body></html>"""


def main():
    p=argparse.ArgumentParser(description="BEAN private management intelligence")
    p.add_argument("--primary-db",required=True,type=Path)
    p.add_argument("--primary-site",default="SITE_A")
    p.add_argument("--peer-db",type=Path)
    p.add_argument("--peer-site",default="SITE_B")
    p.add_argument("--start",required=True)
    p.add_argument("--as-of",required=True)
    p.add_argument("--output",required=True,type=Path,help="Private local HTML output path")
    p.add_argument("--note-file",type=Path,help="Optional private management note")
    args=p.parse_args()
    def site_read(db,code):
        if not db.is_file():raise ValueError("Ledger does not exist: "+str(db))
        ledger=ExportSponge(db)
        try: return analyze_site(code,ledger.report(args.start,args.as_of))
        finally:ledger.close()
    primary=site_read(args.primary_db,args.primary_site)
    peer=site_read(args.peer_db,args.peer_site) if args.peer_db else None
    summary=compare_sites(primary,peer)
    note=args.note_file.read_text(encoding="utf-8") if args.note_file else ""
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(render_html(summary,note),encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"html":str(args.output),"json":str(args.output.with_suffix(".json")),
                      "comparison":summary["comparison"]["state"],"open_gaps":len(summary["gaps"])}))


if __name__=="__main__":
    main()
