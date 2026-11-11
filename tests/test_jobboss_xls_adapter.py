"""Synthetic legacy BIFF fixture tests; never use employer exports in CI."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ezbean.jobboss_exports import ExportSponge
from ezbean.jobboss_xls_adapter import convert, main

try:
    import xlwt
except ImportError:
    xlwt = None


@unittest.skipUnless(xlwt is not None, "Install the optional xlwt test fixture dependency")
class LegacyShipmentAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.layout = self.root / "private-layout.json"
        self.layout.write_text(json.dumps({
            "start_row": 1,
            "record_indicator_column": 6,
            "columns": {
                "PackingList": 0,
                "CustomerCode": 1,
                "DateShipped": 2,
                "DueDate": 3,
                "QtyShipped": 4,
                "JobNumber": 5,
                "DaysEarlyLate": 6,
                "QtyOrdered": 8,
                "Description": 9,
            },
            "inherit": ["PackingList", "CustomerCode"],
            "trailer": {"field": "PONumber", "column": 7,
                        "pattern": r"PO:\s*(.+)"},
        }), encoding="utf-8")
        self.source = self.root / "generic-test.xls"
        wb = xlwt.Workbook()
        sh = wb.add_sheet("Generic shipments")
        def row(ix, values):
            for c, value in enumerate(values):
                if value is not None:
                    sh.write(ix, c, value)
        row(0, ["Packing List", "Customer", "Shipped", "Due", "Qty",
                "Job", "Days", "PO", "Qty ordered", "Description"])
        row(1, ["PACK1", "FICTIONAL", "11/02/2026", "11/02/2026",
                4, "JOB1", 0, None, 4, "Example A"])
        row(2, ["Packing List", "Customer", "Shipped", "Due", "Qty",
                "Job", "Days", "PO", "Qty ordered", "Description"])
        row(3, [None, None, "11/05/2026", "11/02/2026",
                2, "JOB2", 3, None, 5, "Example B"])
        row(4, ["PACK2", "FICTIONAL", "11/02/2026", "11/02/2026",
                1, None, 0, None, 0, "No job on source line"])
        row(5, [None, None, None, None, None, None, None, "PO: TEST-456"])
        row(6, ["Total", None, None, None, 7, None, 3])
        wb.save(str(self.source))

    def test_line_marker_not_job_number_preserves_unverifiable_lines(self):
        rows, evidence = convert(self.source, self.layout, expected_lines=3, expected_late=1)
        self.assertEqual((len(rows), evidence["late"], evidence["missing_job_lines"]), (3, 1, 1))
        self.assertEqual(rows[1]["PackingList"], "PACK1")
        self.assertEqual(rows[1]["CustomerCode"], "FICTIONAL")
        self.assertEqual(rows[2]["JobNumber"], "")
        self.assertEqual(rows[2]["PONumber"], "TEST-456")
        self.assertEqual(rows[2]["QtyOrdered"], "0")
        self.assertEqual(len(evidence["source_sha256"]), 64)

    def test_roundtrip_into_existing_csv_importer_without_second_ledger(self):
        argv = ["jobboss_xls_adapter", "--source", str(self.source),
                "--layout", str(self.layout),
                "--expected-lines", "3", "--expected-late", "1",
                "--output", str(self.root / "private.csv")]
        with patch.object(sys, "argv", argv):
            main()
        with (self.root / "private.csv").open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 3)
        store = ExportSponge(self.root / "private.db")
        try:
            imported = store.ingest(self.root / "private.csv",
                                    captured_at="2026-11-10T21:00:00Z")
            self.assertEqual(imported["status"], "imported")
            self.assertEqual(imported["kind"], "shipment_summary")
            self.assertEqual(imported["rows"], 3)
            self.assertEqual(store.ingest(self.root / "private.csv",
                                  captured_at="2026-11-10T21:00:00Z")["status"], "duplicate")
        finally:
            store.close()
        with patch.object(sys, "argv", argv):
            with self.assertRaises(FileExistsError):
                main()

    def test_reconciliation_failure_does_not_create_output(self):
        dest = self.root / "never-created.csv"
        argv = ["jobboss_xls_adapter", "--source", str(self.source),
                "--layout", str(self.layout), "--expected-lines", "4",
                "--expected-late", "1", "--output", str(dest)]
        with patch.object(sys, "argv", argv):
            with self.assertRaisesRegex(ValueError, "Reconciliation failed"):
                main()
        self.assertFalse(dest.exists())
        with self.assertRaisesRegex(ValueError, "Reconciliation failed"):
            convert(self.source, self.layout, expected_lines=3, expected_late=0)

    def test_write_failure_removes_only_new_partial_output(self):
        dest = self.root / "incomplete.csv"
        argv = ["jobboss_xls_adapter", "--source", str(self.source),
                "--layout", str(self.layout),
                "--expected-lines", "3", "--expected-late", "1",
                "--output", str(dest)]
        with patch.object(sys, "argv", argv):
            with patch("ezbean.jobboss_xls_adapter.csv.DictWriter") as writer:
                writer.return_value.writerows.side_effect = OSError("synthetic disk failure")
                with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                    main()
        self.assertFalse(dest.exists())
        dest.write_text("PRESERVE EXISTING", encoding="utf-8")
        with patch.object(sys, "argv", argv):
            with self.assertRaises(FileExistsError):
                main()
        self.assertEqual(dest.read_text(encoding="utf-8"), "PRESERVE EXISTING")

    def test_wrong_map_bad_file_and_unknown_headers_fail_closed(self):
        self.layout.write_text(json.dumps({
            "start_row": 0, "record_indicator_column": 6,
            "columns": {"PackingList": 0}
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "requires"):
            convert(self.source, self.layout, expected_lines=3, expected_late=1)
        fake = self.root / "fake.xls"
        fake.write_text("not an OLE workbook", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Not a legacy"):
            convert(fake, self.layout, expected_lines=3, expected_late=1)
        with self.assertRaisesRegex(ValueError, "positive"):
            convert(self.source, self.layout, expected_lines=0, expected_late=0)


if __name__ == "__main__":
    unittest.main()
