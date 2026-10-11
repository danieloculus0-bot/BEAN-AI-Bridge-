"""JobBOSS spreadsheet intake for BEAN Bridge; no ERP credentials or network access.

Supports exported Job Schedule CSV, Shipment Summary CSV and RMA Tracker XLSX.
Every import is an immutable local source snapshot; no user data belongs in git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import posixpath
import re
import sqlite3
import time
import zipfile
from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

UTC = timezone.utc
MAX_SOURCE_SIZE = 35_000_000
MAX_UNCOMPRESSED = 90_000_000
JOB_HEADERS = {"JobNumber","CustomerCode","QtyOrdered","DueDate","QtyShipped","ShippedDate"}
SHIP_HEADERS = {"PackingList","JobNumber","DateShipped","DueDate","QtyShipped"}
RMA_HEADERS = {"Date","Order Number","Customer","Department","Person","Defect Description","Reason Code"}
NS = {"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p":"http://schemas.openxmlformats.org/package/2006/relationships"}


def _timestamp(value):
    if isinstance(value, datetime):
        d=value
    elif isinstance(value,str):
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
    else:
        raise ValueError("Timestamp must be explicit")
    if d.tzinfo is None:
        raise ValueError("Timestamp must have a timezone")
    return d.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00","Z")


def _file_timestamp(path):
    name=Path(path).stem
    m=re.search(r"(20\d{2})-(\d{2})-(\d{2})T(\d{2})(\d{2})(\d{2})",name)
    if m:
        return _timestamp(datetime(*map(int,m.groups()),tzinfo=UTC))
    m=re.search(r"(20\d{2})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})",name)
    if m:
        return _timestamp(datetime(*map(int,m.groups()),tzinfo=UTC))
    # File mtime is not a reliable ERP event timestamp, so caller must choose
    # an explicit capture time rather than silently invent provenance.
    raise ValueError("Cannot identify export timestamp from filename; supply --captured-at")


def _rows_csv(path):
    with Path(path).open(newline="",encoding="utf-8-sig") as fh:
        rows=csv.DictReader(fh)
        if rows.fieldnames is None:
            raise ValueError("CSV header missing")
        headers=[x.strip() if x is not None else "" for x in rows.fieldnames]
        if len(set(headers)) != len(headers) or not all(headers):
            raise ValueError("CSV has blank or repeated headers")
        for idx,row in enumerate(rows,start=2):
            if None in row:
                raise ValueError(f"Unexpected CSV columns at row {idx}")
            if not any(str(x or "").strip() for x in row.values()):
                continue
            yield idx,{str(k).strip():str(v or "").strip() for k,v in row.items()}


def _col_index(value):
    letters=re.match(r"[A-Z]+",value)
    if not letters: raise ValueError("Unexpected XLSX cell coordinate")
    num=0
    for x in letters.group():num=num*26+ord(x)-64
    return num-1


def _rows_xlsx(path,sheet_name="RMA Log"):
    """Read values from an XLSX without executing macros/formulas or modifying it."""
    with zipfile.ZipFile(path) as z:
        if sum(x.file_size for x in z.infolist()) > MAX_UNCOMPRESSED:
            raise ValueError("XLSX expanded size too large")
        workbook=ET.fromstring(z.read("xl/workbook.xml"))
        relmap={r.attrib["Id"]:r.attrib["Target"] for r in
                ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        target=None
        for sh in workbook.findall(".//m:sheets/m:sheet",NS):
            if sh.attrib.get("name")==sheet_name:
                target=relmap[sh.attrib["{"+NS["r"]+"}id"]]
        if target is None:
            raise ValueError("Workbook has no RMA Log sheet")
        filepath=(target.lstrip("/") if target.startswith("/") else
                  posixpath.normpath(posixpath.join("xl",target)))
        shared=[]
        if "xl/sharedStrings.xml" in z.namelist():
            root=ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared=["".join(t.text or "" for t in e.findall(".//m:t",NS))
                    for e in root.findall("m:si",NS)]
        xml=ET.fromstring(z.read(filepath))
        for row in xml.findall(".//m:sheetData/m:row",NS):
            vals={}
            for cell in row.findall("m:c",NS):
                ix=_col_index(cell.attrib["r"])
                kind=cell.attrib.get("t")
                value=cell.findtext("m:v",default="",namespaces=NS)
                if kind=="s":
                    value=shared[int(value)]
                elif kind=="inlineStr":
                    value="".join(x.text or "" for x in cell.findall(".//m:t",NS))
                vals[ix]=value
            if not vals: continue
            yield int(row.attrib["r"]),[vals.get(i,"") for i in range(max(vals)+1)]


def _rows_rma(path):
    it=iter(_rows_xlsx(path))
    try:
        _,headers=next(it)
    except StopIteration:
        raise ValueError("RMA sheet is empty") from None
    headers=[str(v).strip() for v in headers]
    if not RMA_HEADERS.issubset(set(headers)):
        raise ValueError("RMA Log headers do not match supported tracker layout")
    for idx,vals in it:
        row={k:str(vals[i] if i<len(vals) else "").strip()
             for i,k in enumerate(headers) if k}
        if row.get("Order Number") or row.get("Defect Description"):
            yield idx,row


def _calendar_date(value,field):
    v=str(value if value is not None else "").strip()
    if not v:return None
    # XLSX serial dates are read as numbers without guessing date styles.
    if re.fullmatch(r"\d+(?:\.0+)?",v):
        d=date(1899,12,30)+timedelta(days=int(float(v)))
        if not date(1990,1,1)<=d<=date(2100,12,31):
            raise ValueError(f"Unsupported {field} serial date")
        return d
    for fmt in ("%m/%d/%Y","%Y-%m-%d","%m/%d/%y"):
        try:return datetime.strptime(v,fmt).date()
        except ValueError:pass
    raise ValueError(f"Unsupported {field} date format")


def _count(value,field,empty=0):
    value=str(value if value is not None else "").strip()
    if not value:return empty
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.0+)?",value):
        raise ValueError(f"{field} must be nonnegative whole units")
    try:
        n=Decimal(value.replace(",",""))
        if not n.is_finite() or n<0 or n!=n.to_integral_value():
            raise ValueError()
        return int(n)
    except (InvalidOperation,ValueError):
        raise ValueError(f"{field} must be nonnegative whole units") from None


def _source(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_SOURCE_SIZE:
        raise ValueError("Source file missing or oversized")
    if path.suffix.lower()==".xlsx":
        rows=list(_rows_rma(path))
        return "rma_tracker",rows
    if path.suffix.lower()!=".csv":
        raise ValueError("Only CSV and XLSX JobBOSS exports are supported")
    rows=list(_rows_csv(path))
    if not rows:raise ValueError("Empty report: no rows to identify schema")
    keys=set(rows[0][1])
    if JOB_HEADERS.issubset(keys):
        return "job_schedule",rows
    if SHIP_HEADERS.issubset(keys):
        return "shipment_summary",rows
    raise ValueError("CSV columns do not match Job Schedule or Shipment Summary")


class ExportSponge:
    def __init__(self, database):
        self.db=sqlite3.connect(str(database))
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS export_snapshots(
            digest TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            source_name TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS export_rows(
            digest TEXT NOT NULL REFERENCES export_snapshots(digest),
            row_number INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(digest,row_number)
        );
        CREATE INDEX IF NOT EXISTS snap_lookup ON export_snapshots(kind,captured_at);
        CREATE TABLE IF NOT EXISTS import_issues(
            digest TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            issue TEXT NOT NULL,
            PRIMARY KEY(digest,row_number)
        );
        """)
        self.db.commit()

    def ingest(self,path,captured_at=None):
        path=Path(path)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        previous=self.db.execute("SELECT kind,row_count FROM export_snapshots WHERE digest=?",(digest,)).fetchone()
        if previous:
            warnings=self.db.execute("SELECT COUNT(*) FROM import_issues WHERE digest=?",(digest,)).fetchone()[0]
            return {"status":"duplicate","kind":previous["kind"],"rows":previous["row_count"],
                    "quarantined_rows":warnings,"digest":digest}
        stamp=_timestamp(captured_at) if captured_at else _file_timestamp(path)
        kind,rows=_source(path)
        # Quarantine malformed RMA tracker dates instead of losing the whole
        # historical export; other report schema errors fail the batch.
        issues=[]
        for idx,row in rows:
            if kind=="job_schedule":
                _calendar_date(row["DueDate"],"DueDate")
                _calendar_date(row.get("ShippedDate"),"ShippedDate")
                _count(row.get("QtyOrdered"),"QtyOrdered")
                _count(row.get("QtyShipped"),"QtyShipped")
            elif kind=="shipment_summary":
                if not _calendar_date(row["DateShipped"],"DateShipped") or not _calendar_date(row["DueDate"],"DueDate"):
                    raise ValueError(f"Shipment dates missing at row {idx}")
                _count(row.get("QtyShipped"),"QtyShipped")
            elif kind=="rma_tracker":
                try:
                    if not _calendar_date(row.get("Date"),"Date"):
                        raise ValueError("RMA date missing")
                except ValueError as exc:
                    issues.append((digest,idx,str(exc)[:180]))
        now=_timestamp(datetime.now(UTC))
        with self.db:
            self.db.execute("INSERT INTO export_snapshots VALUES(?,?,?,?,?,?)",
                            (digest,kind,stamp,path.name,len(rows),now))
            self.db.executemany("INSERT INTO export_rows VALUES(?,?,?)",
                    [(digest,idx,json.dumps(row,sort_keys=True,ensure_ascii=False)) for idx,row in rows])
            self.db.executemany("INSERT INTO import_issues VALUES(?,?,?)",issues)
        return {"status":"imported","kind":kind,"rows":len(rows),
                "quarantined_rows":len(issues),"digest":digest}

    def snapshots(self,kind,as_of):
        rows=self.db.execute("""
            SELECT * FROM export_snapshots WHERE kind=? AND captured_at<=?
            ORDER BY captured_at DESC,imported_at DESC,digest DESC
        """,(kind,_timestamp(as_of))).fetchall()
        return rows

    def records(self,snapshot):
        if snapshot is None:return []
        return [(f"{snapshot['digest'][:12]}:{row['row_number']}",
                 json.loads(row["payload_json"])) for row in self.db.execute(
                 """SELECT row_number,payload_json FROM export_rows
                    WHERE digest=? AND NOT EXISTS (
                       SELECT 1 FROM import_issues i
                       WHERE i.digest=export_rows.digest AND i.row_number=export_rows.row_number)
                    ORDER BY row_number""",(snapshot["digest"],))]

    def report(self,window_start,as_of):
        start=date.fromisoformat(window_start)
        end=datetime.fromisoformat(_timestamp(as_of).replace("Z","+00:00")).date()
        if start>end:raise ValueError("Window begins after report as-of")
        schedule=self.snapshots("job_schedule",as_of)
        shipment=self.snapshots("shipment_summary",as_of)
        rma=self.snapshots("rma_tracker",as_of)
        active_schedule=schedule[0] if schedule else None
        active_rma=rma[0] if rma else None
        due=[]
        due_date_lines=0
        unverified_shipping_state=0
        for ref,row in self.records(active_schedule):
            due_date=_calendar_date(row.get("DueDate"),"DueDate")
            if due_date is None or not due_date<end:continue
            ordered=_count(row.get("QtyOrdered"),"QtyOrdered")
            if ordered<=0:continue
            due_date_lines+=1
            shipped_text=str(row.get("QtyShipped") or "").strip()
            if not shipped_text:
                # Missing QtyShipped is UNKNOWN, not zero, even if QtyOrdered exists.
                unverified_shipping_state+=1
                continue
            shipped=_count(shipped_text,"QtyShipped")
            if ordered>shipped:due.append(ref)
        # Shipments are accumulated across file snapshots. Identical shipment
        # identities in a newer export replace the previous view of that line.
        shipped={}
        for snap in reversed(shipment):
            same_file=set()
            for ref,row in self.records(snap):
                if not all(str(row.get(k,"")).strip() for k in ("PackingList","JobNumber","DateShipped")):
                    continue
                identity=(row["PackingList"],row["JobNumber"],row["DateShipped"],
                          row.get("OrderNumber",""),row.get("Description",""))
                if identity in same_file:
                    raise ValueError("Ambiguous duplicate shipment identity within one export")
                same_file.add(identity)
                shipped[identity]=(ref,row)
        shipment_rows=[]
        for ref,row in shipped.values():
            shipped_date=_calendar_date(row.get("DateShipped"),"DateShipped")
            if start<=shipped_date<=end and _count(row.get("QtyShipped"),"QtyShipped")>0:
                shipment_rows.append((ref,row))
        shipped_on_time=[(ref,row) for ref,row in shipment_rows
            if _calendar_date(row.get("DateShipped"),"DateShipped") <= _calendar_date(row.get("DueDate"),"DueDate")]
        verified_early_late=0
        conflicting_early_late=0
        missing_early_late=0
        partially_shipped=0
        for _,row in shipment_rows:
            actual_days=(_calendar_date(row["DateShipped"],"DateShipped")-
                         _calendar_date(row["DueDate"],"DueDate")).days
            source_days=str(row.get("DaysEarlyLate") or "").strip()
            if not source_days:
                missing_early_late+=1
            else:
                try:
                    reported=Decimal(source_days.replace(",",""))
                    if reported.is_finite() and reported==actual_days:
                        verified_early_late+=1
                    else:
                        conflicting_early_late+=1
                except InvalidOperation:
                    conflicting_early_late+=1
            if row.get("QtyOrdered","").strip() and _count(row["QtyShipped"],"QtyShipped") < _count(row["QtyOrdered"],"QtyOrdered"):
                partially_shipped+=1
        rmas=[]
        for ref,row in self.records(active_rma):
            rma_date=_calendar_date(row.get("Date"),"Date")
            if start<=rma_date<=end:rmas.append((ref,row))
        reason_counts=dict(Counter(row["Reason Code"] for _,row in rmas if row.get("Reason Code")))
        quarantined=[{"row_ref":f"{active_rma['digest'][:12]}:{q['row_number']}",
                      "issue":q["issue"]} for q in self.db.execute(
            "SELECT row_number,issue FROM import_issues WHERE digest=? ORDER BY row_number",
            (active_rma["digest"],))] if active_rma else []
        otd=(round(100*len(shipped_on_time)/len(shipment_rows),2) if shipment_rows else None)
        return {
          "schema":"BEAN_JOBBOSS_EXPORT_V1",
          "window_start":window_start,"as_of":_timestamp(as_of),
          "classification":"source_export_calculation_not_live_ERP",
          "source_snapshots":{
              "job_schedule":active_schedule["digest"][:12] if active_schedule else None,
              "shipment_summary_count":len(shipment),
              "rma_tracker":active_rma["digest"][:12] if active_rma else None},
          "metrics":{
              "otd_percent_by_shipment_line":otd,
              "shipment_lines":len(shipment_rows) if shipment else None,
              "on_time_shipment_lines":len(shipped_on_time) if shipment else None,
              "partially_shipped_lines":partially_shipped if shipment else None,
              "past_due_open_job_lines":(len(due) if schedule and not unverified_shipping_state else None),
              "schedule_due_date_lines":due_date_lines if schedule else None,
              "schedule_missing_shipped_quantity_lines":unverified_shipping_state if schedule else None,
              "rma_entries":len(rmas) if rma else None,
              "rma_missing_reason_entries":sum(not row.get("Reason Code") for _,row in rmas) if rma else None,
              "rma_quantity":None,
              "rma_cost_usd":None},
          "rma_reason_counts":reason_counts if rma else None,
          "source_verification":{"shipment_days_early_late":{
              "status":("not_available" if not shipment_rows else
                        "conflicted" if conflicting_early_late else
                        "verified" if verified_early_late==len(shipment_rows) else "unknown"),
              "reconciled_lines":verified_early_late,
              "unavailable_lines":missing_early_late,
              "conflicting_lines":conflicting_early_late}},
          "quarantined_rma_rows":quarantined,
          "evidence":{
              "shipment_row_refs":[ref for ref,_ in shipment_rows],
              "past_due_row_refs":due,
              "rma_row_refs":[ref for ref,_ in rmas]},
          "limitations":[
              "OTD denominator is shipped report lines, not complete jobs or orders.",
              "Shipment exports are merged by packing list, job, date, order and description; source coverage must be verified.",
              "Job Schedule is a captured snapshot; only the latest available schedule is used.",
              "Missing job shipped quantity makes open/past-due status N/A, not zero.",
              "RMA Tracker records incidents but does not include reliable quantity or dollar columns.",
              "Malformed RMA dates are quarantined and excluded, with row-level audit evidence.",
              "A missing export is unknown (null), not a zero count.",
              "All source spreadsheets and the SQLite ledger remain local; no ERP write-back."
          ]}

    def close(self):
        self.db.close()


def scan_folder(folder,store,stable_seconds=3):
    folder=Path(folder)
    if not folder.is_dir():raise ValueError("Input directory not found")
    result=[]
    for path in sorted(folder.iterdir()):
        if not path.is_file():continue
        name=path.name.casefold()
        if not (("job schedule" in name or "shipment summary" in name or
                 "rma_tracker" in name or "rma tracker" in name) and
                path.suffix.casefold() in (".csv",".xlsx")):
            continue
        if stable_seconds > 0 and time.time()-path.stat().st_mtime < stable_seconds:
            continue
        try:result.append({"file":path.name,**store.ingest(path)})
        except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
            result.append({"file":path.name,"status":"rejected","error":str(exc)[:250]})
    return result


def main():
    p=argparse.ArgumentParser(description="BEAN JobBOSS read-only export sponge")
    p.add_argument("--database",type=Path,default=Path("jobboss_sponge.sqlite"))
    sub=p.add_subparsers(dest="action",required=True)
    import_p=sub.add_parser("import")
    import_p.add_argument("files",nargs="+",type=Path)
    import_p.add_argument("--captured-at")
    watch=sub.add_parser("watch")
    watch.add_argument("folder",type=Path)
    watch.add_argument("--interval",type=float,default=10)
    scan=sub.add_parser("scan")
    scan.add_argument("folder",type=Path)
    report=sub.add_parser("report")
    report.add_argument("--start",required=True)
    report.add_argument("--as-of",required=True)
    report.add_argument("--out",type=Path,default=Path("jobboss_output.json"))
    args=p.parse_args()
    store=ExportSponge(args.database)
    try:
        if args.action=="import":
            print(json.dumps([store.ingest(f,args.captured_at) for f in args.files],indent=2))
        elif args.action=="scan":
            print(json.dumps(scan_folder(args.folder,store),indent=2))
        elif args.action=="watch":
            if args.interval<1:raise ValueError("Poll interval must be >= 1 second")
            try:
                while True:
                    updates=scan_folder(args.folder,store)
                    changed=[r for r in updates if r["status"]!="duplicate"]
                    if changed:print(json.dumps(changed),flush=True)
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                return
        else:
            output=store.report(args.start,args.as_of)
            args.out.parent.mkdir(parents=True,exist_ok=True)
            args.out.write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
            print(json.dumps({"written":str(args.out),"metrics":output["metrics"]},indent=2))
    finally:store.close()


if __name__=="__main__":main()
