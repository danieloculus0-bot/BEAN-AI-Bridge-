"""Private, configurable BIFF .xls shipment export adapter.

Only synthetic layouts belong in this public repository. Keep actual column
maps, source reports, and converted CSV files in authorized private storage.
This module produces the existing shipment CSV schema; it creates no ledger.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .jobboss_exports import (
    MAX_SOURCE_SIZE, SHIP_HEADERS, _calendar_date, _count,
)

FIELDS = (
    "PackingList", "OrderNumber", "CustomerCode", "DateShipped", "DueDate",
    "DaysEarlyLate", "DaysInHouse", "JobNumber", "Description", "QtyOrdered",
    "QtyShipped", "PONumber",
)
DATES = {"DateShipped", "DueDate"}
INHERITABLE = {"PackingList", "OrderNumber", "CustomerCode", "DateShipped"}
ANCHOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


def _layout(path):
    layout = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(layout, dict):
        raise ValueError("Layout must be a JSON object")
    start = layout.get("start_row")
    marker = layout.get("record_indicator_column")
    columns = layout.get("columns")
    if type(start) is not int or start < 0:
        raise ValueError("start_row must be a zero-based nonnegative integer")
    if type(marker) is not int or marker < 0:
        raise ValueError("record_indicator_column must be a zero-based column")
    if not isinstance(columns, dict) or not SHIP_HEADERS.issubset(columns):
        raise ValueError("Layout requires all canonical shipment columns")
    if not set(columns).issubset(FIELDS):
        raise ValueError("Unknown canonical shipment column")
    if any(type(i) is not int or i < 0 or i > 255 for i in columns.values()):
        raise ValueError("Column indices must be integers between 0 and 255")
    inherit = layout.get("inherit", ["PackingList", "CustomerCode"])
    if not isinstance(inherit, list) or any(x not in INHERITABLE for x in inherit):
        raise ValueError("Invalid inherit fields")
    trailer = layout.get("trailer")
    if trailer is not None:
        if not isinstance(trailer, dict) or set(trailer) != {"field", "column", "pattern"}:
            raise ValueError("Invalid trailing-field rule")
        if trailer["field"] != "PONumber" or type(trailer["column"]) is not int or not 0 <= trailer["column"] <= 255:
            raise ValueError("Only an explicit PONumber trailing-field rule is supported")
        if not isinstance(trailer["pattern"], str) or len(trailer["pattern"]) > 200:
            raise ValueError("Invalid trailing-field pattern")
        pattern = re.compile(trailer["pattern"])
        if pattern.groups != 1:
            raise ValueError("Trailing pattern must have exactly one capture group")
    if any(key not in {"start_row", "record_indicator_column", "columns",
                       "inherit", "trailer", "sheet_index"} for key in layout):
        raise ValueError("Unknown layout key")
    sheet = layout.get("sheet_index", 0)
    if type(sheet) is not int or sheet < 0:
        raise ValueError("sheet_index must be a nonnegative integer")
    return layout


def _numeric(value):
    if isinstance(value, bool):
        return False
    try:
        return bool(str(value).strip()) and Decimal(str(value).strip().replace(",", "")).is_finite()
    except (InvalidOperation, TypeError, ValueError):
        return False


def _cell(sheet, row, index, workbook, xlrd, *, as_date=False):
    if index >= sheet.ncols:
        return ""
    c = sheet.cell(row, index)
    if c.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return ""
    value = c.value
    if as_date and (c.ctype == xlrd.XL_CELL_DATE or
                    c.ctype == xlrd.XL_CELL_NUMBER and 20000 <= value <= 100000):
        return xlrd.xldate_as_datetime(value, workbook.datemode).date().isoformat()
    if c.ctype == xlrd.XL_CELL_NUMBER:
        if value.is_integer():
            return str(int(value))
        return str(value)
    if c.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(value, workbook.datemode).date().isoformat()
    return str(value).strip()


def convert(source, layout_path, *, expected_lines, expected_late):
    """Parse and reconcile privately. No output is written until all checks pass."""
    path = Path(source)
    if path.suffix.lower() != ".xls" or not path.is_file():
        raise ValueError("Expected an existing legacy .xls source file")
    if path.stat().st_size > MAX_SOURCE_SIZE:
        raise ValueError("Legacy report exceeds import size limit")
    if path.open("rb").read(8) != bytes.fromhex("D0CF11E0A1B11AE1"):
        raise ValueError("Not a legacy OLE/BIFF .xls workbook")
    if type(expected_lines) is not int or expected_lines <= 0:
        raise ValueError("A positive independent expected line count is required")
    if type(expected_late) is not int or not 0 <= expected_late <= expected_lines:
        raise ValueError("An independent expected late count is required")
    layout = _layout(layout_path)
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("Install the optional private XLS dependency: pip install xlrd==2.0.2") from exc
    book = xlrd.open_workbook(str(path), on_demand=True)
    try:
        if layout.get("sheet_index", 0) >= book.nsheets:
            raise ValueError("Configured sheet is absent")
        sheet = book.sheet_by_index(layout.get("sheet_index", 0))
        if layout["start_row"] >= sheet.nrows:
            raise ValueError("start_row is outside the workbook")
        columns = layout["columns"]
        carry = {}
        rows = []
        for i in range(layout["start_row"], sheet.nrows):
            values = {key: _cell(sheet, i, col, book, xlrd, as_date=key in DATES)
                      for key, col in columns.items()}
            indicator = _cell(sheet, i, layout["record_indicator_column"], book, xlrd)
            if not _numeric(indicator):
                # A report's repeated page headers and prose are not shipment lines.
                anchor = values.get("PackingList", "")
                if ANCHOR.fullmatch(anchor):
                    for key in layout.get("inherit", ["PackingList", "CustomerCode"]):
                        if values.get(key):
                            carry[key] = values[key]
                trailer = layout.get("trailer")
                if trailer and rows:
                    suffix = _cell(sheet, i, trailer["column"], book, xlrd)
                    match = re.fullmatch(trailer["pattern"], suffix)
                    if match:
                        rows[-1][trailer["field"]] = match.group(1).strip()
                continue

            # A numeric subtotal with no shipment fields is not a line.
            supplied = [values.get(k, "") for k in ("DateShipped", "DueDate", "QtyShipped")]
            if not any(supplied):
                continue
            if not all(supplied):
                raise ValueError(f"Incomplete shipment row at source row {i + 1}")
            for key in layout.get("inherit", ["PackingList", "CustomerCode"]):
                if values.get(key):
                    carry[key] = values[key]
                elif key in carry:
                    values[key] = carry[key]
            if not values.get("PackingList"):
                raise ValueError(f"PackingList missing at source row {i + 1}")
            shipped = _calendar_date(values["DateShipped"], "DateShipped")
            due = _calendar_date(values["DueDate"], "DueDate")
            if shipped is None or due is None:
                raise ValueError(f"Shipment dates missing at source row {i + 1}")
            _count(values["QtyShipped"], "QtyShipped")
            if values.get("QtyOrdered"):
                _count(values["QtyOrdered"], "QtyOrdered")
            record = {key: str(values.get(key, "")).strip() for key in FIELDS}
            rows.append(record)
        late = sum(_calendar_date(x["DateShipped"], "DateShipped") >
                   _calendar_date(x["DueDate"], "DueDate") for x in rows)
        if len(rows) != expected_lines or late != expected_late:
            raise ValueError(
                f"Reconciliation failed: {len(rows)} of {expected_lines} expected lines; "
                f"{late} of {expected_late} expected late"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return rows, {"status": "reconciled", "lines": len(rows),
                      "late": late, "missing_job_lines": sum(not x["JobNumber"] for x in rows),
                      "source_sha256": digest}
    finally:
        book.release_resources()


def main():
    parser = argparse.ArgumentParser(description="Private legacy BIFF shipment report adapter")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True, help="Private JSON field map; never commit")
    parser.add_argument("--expected-lines", type=int, required=True, help="Independent breakdown total")
    parser.add_argument("--expected-late", type=int, required=True, help="Independent breakdown late total")
    parser.add_argument("--output", type=Path, help="New private CSV; never overwrites")
    args = parser.parse_args()
    rows, summary = convert(args.source, args.layout,
                            expected_lines=args.expected_lines,
                            expected_late=args.expected_late)
    if args.output:
        # A failed reconciliation never creates output, and an existing file is
        # never overwritten. Source and output must remain on authorized storage.
        with args.output.open("x", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        summary["output_created"] = True
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
