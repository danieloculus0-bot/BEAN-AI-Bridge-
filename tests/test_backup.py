"""Operational pilot backup tests exercise WAL snapshots and real restore."""
import sqlite3
import json
from contextlib import closing
import tempfile
from pathlib import Path
import unittest

from ezbean.backup import backup, restore_drill, check_database, verify_backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "private.sqlite"
        self.connection = sqlite3.connect(str(self.db))
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, note TEXT)")
        self.connection.execute("INSERT INTO events(note) VALUES ('synthetic-observation')")
        self.connection.commit()
        self.addCleanup(self.connection.close)

    def test_online_wal_snapshot_restores_in_new_database(self):
        output = self.folder / "backups" / "test-01.sqlite"
        result = backup(self.db, output)
        self.assertEqual(result["restored_integrity"], "ok")
        self.assertEqual(result["restored_tables"], ["events"])
        self.assertEqual(restore_drill(output)["integrity"], "ok")
        self.assertTrue(output.with_suffix(".sqlite.receipt.json").is_file())
        with closing(sqlite3.connect(str(output))) as copied:
            self.assertEqual(
                copied.execute("SELECT note FROM events").fetchone()[0],
                "synthetic-observation"
            )
        self.connection.execute("INSERT INTO events(note) VALUES ('later')")
        self.connection.commit()
        with closing(sqlite3.connect(str(output))) as copied:
            self.assertEqual(copied.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_backup_receipt_must_match_bytes_and_restore(self):
        path = self.folder / "snapshot.sqlite"
        initial = backup(self.db, path)
        result = verify_backup(path)
        self.assertTrue(result["receipt_verified"])
        self.assertEqual(result["snapshot_sha256"], initial["snapshot_sha256"])
        receipt = path.with_suffix(".sqlite.receipt.json")
        manifest = json.loads(receipt.read_text())
        manifest["snapshot_sha256"] = "f" * 64
        receipt.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            verify_backup(path)

    def test_snapshot_verification_requires_its_receipt(self):
        path = self.folder / "snapshot.sqlite"
        backup(self.db, path)
        path.with_suffix(".sqlite.receipt.json").unlink()
        with self.assertRaises(FileNotFoundError):
            verify_backup(path)

    def test_existing_snapshot_refused_without_overwrite(self):
        output = self.folder / "out.sqlite"
        backup(self.db, output)
        with self.assertRaises(FileExistsError):
            backup(self.db, output)

    def test_missing_or_invalid_snapshot_never_reported_recovered(self):
        with self.assertRaises(FileNotFoundError):
            backup(self.folder / "missing.sqlite", self.folder / "copy.sqlite")
        corrupt = self.folder / "corrupt.sqlite"
        corrupt.write_bytes(b"this is not a valid SQLite file")
        with self.assertRaises(sqlite3.DatabaseError):
            restore_drill(corrupt)
        self.assertEqual(check_database(self.db)["integrity"], "ok")


if __name__ == "__main__":
    unittest.main()
