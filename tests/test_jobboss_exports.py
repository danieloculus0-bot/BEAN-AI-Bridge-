"""Synthetic smoke tests for JobBOSS export sponge; never publish user ERP data."""
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ezbean.jobboss_exports import ExportSponge,scan_folder,_file_timestamp

JOB_FIELDS=["JobNumber","Priority","CustomerCode","PONum","PartNumber","RelType",
            "QtyOrdered","DueDate","QtyShipped","ShippedDate","QtyReady2Ship",
            "WorkCenter","JobNotes","Revision","MasterJobNo"]
SHIP_FIELDS=["PackingList","OrderNumber","CustomerCode","DateShipped","DueDate",
             "DaysEarlyLate","DaysInHouse","JobNumber","Description","QtyOrdered",
             "QtyShipped","PONumber"]
RMA_FIELDS=["Date","Order Number","Customer","Department","Person",
            "Defect Description","Reason Code"]

def write_csv(path,fields,rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for row in rows:writer.writerow(row)

def row_job(job,due,ordered,shipped):
    return {"JobNumber":job,"CustomerCode":"SYNTHETIC CUSTOMER",
            "QtyOrdered":str(ordered),"DueDate":due,"QtyShipped":str(shipped),
            "ShippedDate":"", "PartNumber":"TEST PART"}

def row_ship(pack,job,date,due,qty):
    return {"PackingList":pack,"OrderNumber":job,"CustomerCode":"SYNTHETIC CUSTOMER",
            "DateShipped":date,"DueDate":due,"JobNumber":job,
            "Description":"Fixture shipment","QtyOrdered":str(qty),
            "QtyShipped":str(qty)}

def write_xlsx(path,values):
    """Minimal XLSX using inline strings, sheet RMA Log; no external library."""
    ns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rns="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pns="http://schemas.openxmlformats.org/package/2006/relationships"
    sheets=[]
    for ix,row in enumerate(values,start=1):
        cells=[]
        for j,val in enumerate(row):
            col=chr(65+j)
            if isinstance(val,(int,float)):
                cell=f'<c r="{col}{ix}"><v>{val}</v></c>'
            else:
                cell=f'<c r="{col}{ix}" t="inlineStr"><is><t>{escape(str(val))}</t></is></c>'
            cells.append(cell)
        sheets.append(f'<row r="{ix}">'+''.join(cells)+"</row>")
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml",
          f'<workbook xmlns="{ns}" xmlns:r="{rns}"><sheets><sheet name="RMA Log" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
          f'<Relationships xmlns="{pns}"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
          f'<worksheet xmlns="{ns}"><sheetData>'+''.join(sheets)+"</sheetData></worksheet>")

class JobBossSpongeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.store=ExportSponge(self.root/"test.sqlite")
    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
    def job(self,name="Job Schedule - Detail Report - 2026-09-30T152734.460.csv",rows=None):
        path=self.root/name
        write_csv(path,JOB_FIELDS,rows if rows is not None else [
            row_job("J1","09/26/2026",5,0),
            row_job("J2","10/15/2026",3,0),
            row_job("J3","09/25/2026",10,10)])
        return path
    def shipment(self,name="Shipment Summary - Detail Report - 2026-09-30T152641.201.csv",rows=None):
        path=self.root/name
        write_csv(path,SHIP_FIELDS,rows if rows is not None else [
            row_ship("P1","J11","9/1/2026","9/3/2026",10),
            row_ship("P2","J12","9/2/2026","9/1/2026",20)])
        return path
    def rma(self,name="RMA_Tracker(20261001-131728).xlsx"):
        path=self.root/name
        # Excel 1900 date serial for 2026-09-03 and 2026-10-03
        from datetime import date
        def serial(x):return (date.fromisoformat(x)-date(1899,12,30)).days
        write_xlsx(path,[RMA_FIELDS,
            [serial("2026-09-03"),"J11","Synthetic Co","Weld","","Bad hole","Dimensional"],
            [serial("2026-10-03"),"J12","Synthetic Co","Powder","","Scratch","Cosmetic"]])
        return path
    def test_import_with_actual_report_headers(self):
        for file in (self.job(),self.shipment(),self.rma()):
            state=self.store.ingest(file)
            self.assertEqual(state["status"],"imported")
            self.assertEqual(self.store.ingest(file)["status"],"duplicate")
        result=self.store.report("2026-09-01","2026-10-01T18:00:00Z")
        k=result["metrics"]
        self.assertEqual(k["otd_percent_by_shipment_line"],50.0)
        self.assertEqual(k["on_time_shipment_lines"],1)
        self.assertEqual(k["shipment_lines"],2)
        self.assertEqual(k["past_due_open_job_lines"],1)
        self.assertEqual(k["rma_entries"],1)
        self.assertIsNone(k["rma_quantity"])
        self.assertIsNone(k["rma_cost_usd"])
        self.assertEqual(result["rma_reason_counts"],{"Dimensional":1})
    def test_without_rma_export_is_unknown_not_zero(self):
        self.store.ingest(self.job())
        result=self.store.report("2026-09-01","2026-10-01T00:00:00Z")
        self.assertIsNone(result["metrics"]["rma_entries"])
        self.assertIsNone(result["metrics"]["otd_percent_by_shipment_line"])
    def test_new_schedule_snapshot_updates_past_due_without_erasing_history(self):
        self.store.ingest(self.job())
        newer=self.job("Job Schedule - Detail Report - 2026-10-02T090000.000.csv",
                       [row_job("J1","09/26/2026",5,5)])
        self.store.ingest(newer)
        old=self.store.report("2026-09-01","2026-10-01T00:00:00Z")
        new=self.store.report("2026-09-01","2026-10-02T12:00:00Z")
        self.assertEqual(old["metrics"]["past_due_open_job_lines"],1)
        self.assertEqual(new["metrics"]["past_due_open_job_lines"],0)
    def test_merge_duplicate_shipment_exports_without_double_count(self):
        self.store.ingest(self.shipment())
        self.store.ingest(self.shipment("Shipment Summary - Detail Report - 2026-10-01T080000.000.csv",
                       [row_ship("P1","J11","9/1/2026","9/3/2026",10),
                        row_ship("P2","J12","9/2/2026","9/1/2026",20),
                        row_ship("P3","J13","9/10/2026","9/10/2026",3)]))
        result=self.store.report("2026-09-01","2026-10-02T00:00:00Z")
        self.assertEqual(result["metrics"]["shipment_lines"],3)
        self.assertAlmostEqual(result["metrics"]["otd_percent_by_shipment_line"],66.67)
    def test_same_snapshot_conflicting_shipments_rejected_for_report(self):
        src=self.shipment(rows=[row_ship("P1","J1","9/1/2026","9/2/2026",4),
                                row_ship("P1","J1","9/1/2026","9/2/2026",9)])
        self.store.ingest(src)
        with self.assertRaisesRegex(ValueError,"Ambiguous"):
            self.store.report("2026-09-01","2026-10-01T00:00:00Z")
    def test_bad_negative_quantities_fail_on_import(self):
        with self.assertRaisesRegex(ValueError,"nonnegative"):
            self.store.ingest(self.shipment(rows=[
               row_ship("P5","J5","9/1/2026","9/2/2026",-4)]))
    def test_no_capture_time_guess_for_renamed_files(self):
        self.assertIn("2026-09-30T15:27:34Z",_file_timestamp(self.job()))
        with self.assertRaisesRegex(ValueError,"captured-at"):
            self.store.ingest(self.job("renamed.csv"))
        self.assertEqual(self.store.ingest(self.job("renamed.csv"),
                         captured_at="2026-10-01T00:00:00Z")["status"],"imported")
    def test_scan_folder_ignores_incomplete_unknown_and_reimports(self):
        self.job()
        self.shipment()
        (self.root/"unrelated.csv").write_text("a,b\n1,2\n")
        result=scan_folder(self.root,self.store,stable_seconds=0)
        self.assertEqual(len(result),2)
        result2=scan_folder(self.root,self.store,stable_seconds=0)
        self.assertTrue(all(r["status"]=="duplicate" for r in result2))
    def test_only_recognized_rma_log_sheet(self):
        path=self.rma()
        self.store.ingest(path)
        self.assertEqual(self.store.report("2026-10-01","2026-10-02T00:00:00Z")["metrics"]["rma_entries"],0)
    def test_future_snapshot_never_used_early(self):
        self.store.ingest(self.job())
        before=self.store.report("2026-09-01","2026-09-29T18:00:00Z")
        self.assertIsNone(before["metrics"]["past_due_open_job_lines"])

if __name__=="__main__":
    unittest.main()
