"""Run the existing BEAN Operations pipeline through one installed command.

The operator explicitly supplies local exports and paths. For first-run
validation, --demo creates fictional exports without accessing any business
system. Neither mode submits data to GitHub or to a hosted model.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import posixpath
import zipfile
from xml.sax.saxutils import escape as xml_escape

from .daily_brief import build_daily_brief, render_html
from .jobboss_exports import ExportSponge, scan_folder
from .management_intelligence import analyze_site

DEFAULT_DEMO_AS_OF = "2026-10-16T18:00:00Z"


def _example_xlsx(path: Path) -> None:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    headers = ["Date", "Order Number", "Customer", "Department", "Person", "Defect Description"]
    days = (date(2026, 10, 12) - date(1899, 12, 30)).days
    rows = [headers, [days, "FICTIONAL-001", "EXAMPLE ONLY", "Weld", "",
                      "Synthetic fixture issue"]]
    sheet = []
    for number, cells in enumerate(rows, 1):
        xml = "".join(
            f'<c r="{chr(65 + idx)}{number}" t="inlineStr"><is><t>{xml_escape(str(cell))}</t></is></c>'
            for idx, cell in enumerate(cells)
        )
        sheet.append(f'<row r="{number}">{xml}</row>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        # A generated XLSX is a ZIP. Default ZIP member timestamps vary by
        # launch time, defeating source SHA deduplication between identical
        # runs. Keep fixture archive bytes deterministic.
        def write_file(name: str, payload: str) -> None:
            member = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, payload)

        write_file(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{rel}">'
            '<sheets><sheet name="RMA Log" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        write_file(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" '
            'Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
        )
        write_file(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetData>{"".join(sheet)}</sheetData></worksheet>',
        )


def _example_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def make_demo_exports(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    _example_csv(
        folder / "Job Schedule - Detail Report - 2026-10-15T110000.000.csv",
        ["JobNumber", "CustomerCode", "QtyOrdered", "DueDate",
         "QtyShipped", "ShippedDate"],
        [{"JobNumber": "FICTIONAL-001", "CustomerCode": "EXAMPLE ONLY",
          "QtyOrdered": "5", "DueDate": "2026-10-14", "QtyShipped": "0",
          "ShippedDate": ""}],
    )
    _example_csv(
        folder / "Shipment Summary - Detail Report - 2026-10-15T110005.000.csv",
        ["PackingList", "JobNumber", "DateShipped", "DueDate",
         "QtyShipped", "QtyOrdered", "DaysEarlyLate"],
        [{"PackingList": "EXAMPLE-P1", "JobNumber": "FICTIONAL-002",
          "DateShipped": "2026-10-15", "DueDate": "2026-10-15",
          "QtyShipped": "3", "QtyOrdered": "3", "DaysEarlyLate": "0"}],
    )
    _example_xlsx(folder / "RMA_Tracker(20261015-110010).xlsx")
    return folder


def run(
    *, database: Path, exports: Path, out: Path, site: str, start: str,
    as_of: str, previous_as_of: str | None = None, synthetic: bool = False,
) -> dict:
    """Import approved snapshots, generate brief and retain run receipt."""
    if out.suffix.lower() != ".html":
        raise ValueError("Output path must end in .html")
    database.parent.mkdir(parents=True, exist_ok=True)
    sponge = ExportSponge(database)
    try:
        imported = scan_folder(exports, sponge, stable_seconds=0)
        if not imported:
            raise ValueError("No recognizable Job Schedule, Shipment Summary or RMA files")
        failed = [entry for entry in imported if entry["status"] == "rejected"]
        if failed:
            raise ValueError(
                "One or more source exports could not be ingested: " +
                ", ".join(x["file"] + " (" + x["error"] + ")" for x in failed)
            )
        current = analyze_site(site, sponge.report(start, as_of))
        previous = (
            analyze_site(site, sponge.report(start, previous_as_of))
            if previous_as_of else None
        )
        brief = build_daily_brief(current, previous)
    finally:
        sponge.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(brief)
    if synthetic:
        html = (
            '<div style="background:#fee2e2;padding:12px;font-weight:bold">'
            "FICTIONAL DEMONSTRATION — NOT ACTUAL BUSINESS METRICS</div>" + html
        )
    report_path = out.with_suffix(".json")
    out.write_text(html, encoding="utf-8")
    report_path.write_text(json.dumps(brief, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    receipt = {
        "schema": "BEAN_OPERATIONAL_RUN_RECEIPT_V1",
        "synthetic": synthetic,
        "actual_business_validation": False,
        "site": brief["site"],
        "as_of": brief["as_of"],
        "source_status": [
            {"kind": row["kind"], "status": row["status"], "sha256": row["digest"]}
            for row in imported
        ],
        "open_exceptions": brief["open_exception_count"],
        "html_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "json_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "html_path": str(out.resolve()),
        "json_path": str(report_path.resolve()),
    }
    receipt_path = out.with_suffix(".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="BEAN Operations: one-command local report")
    parser.add_argument("--demo", action="store_true",
                        help="Generate fictional inputs and report, no ERP connection")
    parser.add_argument("--exports", type=Path, help="Folder of approved local ERP exports")
    parser.add_argument("--database", type=Path, help="Private SQLite evidence database")
    parser.add_argument("--out", type=Path, required=True, help="Private output HTML file")
    parser.add_argument("--site", default="SITE_A")
    parser.add_argument("--start", default="2026-10-01")
    parser.add_argument("--as-of", help="Timezone-aware source cutoff")
    parser.add_argument("--previous-as-of", help="Previous source snapshot cutoff")
    args = parser.parse_args()
    if args.demo:
        exports = make_demo_exports(args.out.parent / "synthetic-exports")
        database = args.database or args.out.parent / "synthetic-ledger.sqlite"
        as_of = args.as_of or DEFAULT_DEMO_AS_OF
    else:
        if args.exports is None or args.database is None or args.as_of is None:
            parser.error("Real export mode requires --exports, --database and --as-of")
        exports, database, as_of = args.exports, args.database, args.as_of
    result = run(
        database=database, exports=exports, out=args.out,
        site="DEMO_ONLY" if args.demo else args.site, start=args.start,
        as_of=as_of, previous_as_of=args.previous_as_of,
        synthetic=args.demo,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
