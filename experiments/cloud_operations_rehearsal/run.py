"""Run an entirely fictional, end-to-end BEAN Operations cloud rehearsal.

This is NOT a customer pilot, independent KPI audit or evidence of time saved.
It uses genuine BEAN import/brief/pilot/backup code, with invented input data.
The script repeats the experiment in independent SQLite directories and compares
sanitized results, so successful CI means reproducible software behavior.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
from xml.sax.saxutils import escape as xml_escape

from ezbean.backup import backup, verify_backup
from ezbean.daily_brief import build_daily_brief, render_html as brief_html
from ezbean.jobboss_exports import ExportSponge
from ezbean.management_intelligence import analyze_site
from ezbean.pilot import load_log, record, report, render_html as pilot_html


WINDOW = "2026-10-01"
DAYS = tuple(
    date(2026, 10, 5) + timedelta(days=i)
    for i in range(12)
    if (date(2026, 10, 5) + timedelta(days=i)).weekday() < 5
)
assert len(DAYS) == 10
SITE = "FICTIONAL_SITE"


def _csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _xlsx(path: Path, rows: list[list]) -> None:
    """Create a tiny fictional 'RMA Log' XLSX using the standard library."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    pieces = []
    for row_num, values in enumerate(rows, 1):
        cells = []
        for col, value in enumerate(values):
            address = f"{chr(65 + col)}{row_num}"
            cells.append(
                f'<c r="{address}" t="inlineStr"><is><t>{xml_escape(str(value))}</t></is></c>'
            )
        pieces.append(f'<row r="{row_num}">' + "".join(cells) + "</row>")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="RMA Log" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        output.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
        )
        output.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetData>{"".join(pieces)}</sheetData></worksheet>',
        )


def _rma(path: Path, *, revised: bool) -> None:
    # Deliberately omit Reason Code: it is OPTIONAL, including the column.
    headers = [
        "Date", "Order Number", "Customer", "Department", "Person",
        "Defect Description",
    ]
    rows = [
        ["2026-10-05", "FAKE-ORDER-1", "Fictional Co", "Weld", "",
         "Fixture-only observation"],
    ]
    if revised:
        rows += [
            ["2026-10-12", "FAKE-ORDER-2", "Fictional Co", "Powder", "",
             "Second fictional observation"],
            ["not-a-date", "FAKE-ORDER-3", "Fictional Co", "Powder", "",
             "Intentional bad-date example"],
        ]
    _xlsx(path, [headers, *rows])


def _shipments(index: int) -> list[dict]:
    result = []
    for j in range(index + 1):
        day = DAYS[j]
        due = day - timedelta(days=1) if j % 3 == 0 else day
        difference = (day - due).days
        # Introduce a source disagreement once, then correct it next snapshot.
        reported = "99" if index == 4 and j == 4 else str(difference)
        result.append({
            "PackingList": f"FIXTURE-PL-{j}", "JobNumber": f"FIXTURE-JOB-{j}",
            "DateShipped": day.isoformat(), "DueDate": due.isoformat(),
            "QtyShipped": "3", "QtyOrdered": "3",
            "DaysEarlyLate": reported, "Description": "Fictional line",
        })
    return result


def _run_once(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    ledger_path = root / "synthetic-exports.sqlite"
    record_path = root / "synthetic-pilot.jsonl"
    backup_path = root / "midpoint.sqlite"
    current_briefs = []
    quality_states = []
    earlier = None
    source = ExportSponge(ledger_path)
    try:
        for index, day in enumerate(DAYS):
            time = day.isoformat() + "T18:00:00Z"
            schedule = root / f"Job Schedule - Detail Report - {day.isoformat()}T120000.000.csv"
            shipping = root / f"Shipment Summary - Detail Report - {day.isoformat()}T120001.000.csv"
            _csv(schedule, [
                "JobNumber", "CustomerCode", "QtyOrdered", "DueDate",
                "QtyShipped", "ShippedDate",
            ], [{
                "JobNumber": f"FIXTURE-JOB-OPEN-{index}",
                "CustomerCode": "FICTIONAL", "QtyOrdered": "5",
                "DueDate": (day - timedelta(days=1)).isoformat(),
                "QtyShipped": str(5 if index % 3 == 0 else 0),
                "ShippedDate": "",
            }])
            _csv(shipping, [
                "PackingList", "JobNumber", "DateShipped", "DueDate",
                "QtyShipped", "QtyOrdered", "DaysEarlyLate", "Description",
            ], _shipments(index))
            source.ingest(schedule)
            source.ingest(shipping)
            if index in (0, 5):
                path = root / f"RMA_Tracker({day.strftime('%Y%m%d')}-120002).xlsx"
                _rma(path, revised=index == 5)
                source.ingest(path)
            summary = analyze_site(SITE, source.report(WINDOW, time))
            brief = build_daily_brief(summary, earlier)
            assert "RMA_REASON_MISSING" not in {
                item["code"] for item in brief["exceptions"]
            }, "Optional RMA reasons must never generate a deficiency"
            quality_states.append(
                summary["metrics"]["shipment_line_otd"]["state"]
            )
            brief_path = root / f"day-{index+1:02d}.json"
            brief_path.write_text(json.dumps(brief, sort_keys=True, indent=2) + "\n",
                                  encoding="utf-8")
            current_briefs.append(brief)
            shown = brief["open_exception_count"]
            # Synthetic human-review labels/time are intentionally NOT observed.
            record(record_path, brief_path, day=day.isoformat(),
                   baseline_minutes=25 + index % 3, bean_minutes=17 + index % 2,
                   confirmed_useful=min(1, shown),
                   false_alerts=min(1, max(0, shown - 1)),
                   missed_issues=0)
            if index == 4:
                snapshot = backup(ledger_path, backup_path)
                assert verify_backup(backup_path)["receipt_verified"]
            earlier = summary
    finally:
        source.close()

    # A midpoint backup is a real snapshot; subsequent source ingestion must
    # not change it. Replay it from another DB file.
    restore_copy = root / "midpoint-restore.sqlite"
    shutil.copyfile(backup_path, restore_copy)
    replay = ExportSponge(restore_copy)
    try:
        replay_summary = analyze_site(SITE, replay.report(
            WINDOW, DAYS[4].isoformat() + "T18:00:00Z"
        ))
        assert replay_summary["metrics"]["shipment_line_otd"]["state"] == quality_states[4]
    finally:
        replay.close()

    assert quality_states[4] == "CONFLICTED", quality_states
    assert quality_states[5] == "VERIFIED", quality_states
    assert "RMA_DATE_QUARANTINE" in {
        g["code"] for g in current_briefs[6]["exceptions"]
    }
    assert current_briefs[-1]["metrics"]["rma_observed"]["observed_lower_bound"] == 2

    pilot = report(load_log(record_path), site=SITE)
    assert pilot["workdays_recorded"] == 10
    assert pilot["pilot_complete"]  # 10 *fictional* entries, NOT a field pilot.
    assert pilot["missed_issues"] == 0  # synthetic fixture assignment
    digest = hashlib.sha256(
        json.dumps({"pilot": pilot, "last_brief": current_briefs[-1],
                    "states": quality_states}, sort_keys=True).encode()
    ).hexdigest()
    return {
        "synthetic": True, "real_customer_pilot": False,
        "production_readiness_verified": False,
        "commercial_value_verified": False,
        "label": "FICTIONAL SOFTWARE REHEARSAL — NOT FIELD PERFORMANCE",
        "workdays_replayed": len(DAYS),
        "report": pilot,
        "source_reconciliation_states": quality_states,
        "rma_reason_codes_optional": True,
        "rma_bad_date_quarantine_tested": True,
        "midpoint_backup_restored": True,
        "backup_receipt_checked": snapshot["schema"] == "BEAN_SQLITE_BACKUP_RECEIPT_V1",
        "normalized_replay_sha256": digest,
        "last_brief": current_briefs[-1],
    }


def run(output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="bean-cloud-rehearsal-a-") as d1:
        first = _run_once(Path(d1))
    with tempfile.TemporaryDirectory(prefix="bean-cloud-rehearsal-b-") as d2:
        second = _run_once(Path(d2))
    if first["normalized_replay_sha256"] != second["normalized_replay_sha256"]:
        raise AssertionError("Independent synthetic run did not reproduce")
    output.mkdir(parents=True, exist_ok=True)
    final = {k: v for k, v in first.items() if k != "last_brief"}
    final["replayed_twice_identically"] = True
    (output / "synthetic_rehearsal.json").write_text(
        json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "synthetic_pilot.html").write_text(
        '<p><strong>FICTIONAL REHEARSAL — NOT ACTUAL CUSTOMER RESULTS</strong></p>'
        + pilot_html(first["report"]), encoding="utf-8"
    )
    (output / "synthetic_last_brief.html").write_text(
        '<p><strong>FICTIONAL SOURCE DATA — NOT REAL KPI EVIDENCE</strong></p>'
        + brief_html(first["last_brief"]), encoding="utf-8"
    )
    return final


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    report_data = run(args.out)
    print(json.dumps({
        "synthetic": True,
        "workdays_replayed": report_data["workdays_replayed"],
        "replayed_twice_identically": report_data["replayed_twice_identically"],
        "normalized_replay_sha256": report_data["normalized_replay_sha256"],
        "output_dir": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
