"""Local SQLite snapshot and restore drill for Bridge pilot ledgers.

Backup SQLite through the online backup API (not by copying a live WAL file).
A successful restore drill opens a *new* temporary SQLite database and checks
its integrity, rather than touching the operational source.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile


def check_database(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    # Existing local ledger is never modified by integrity verification.
    source = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("SQLite integrity check failed: " + str(integrity))
        tables = source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return {
            "integrity": "ok",
            "tables": [r[0] for r in tables],
        }
    finally:
        source.close()


def backup(database: Path, output: Path) -> dict:
    """Create an independent snapshot with a documented checksum and drill."""
    if not database.is_file():
        raise FileNotFoundError(database)
    if output.exists():
        raise FileExistsError("Backup already exists; choose a new filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(str(output))
    try:
        source.backup(target)
        target.commit()
    except Exception:
        target.close()
        source.close()
        output.unlink(missing_ok=True)
        raise
    else:
        target.close()
        source.close()
    try:
        verified = restore_drill(output)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    manifest = {
        "schema": "BEAN_SQLITE_BACKUP_RECEIPT_V1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_filename": output.name,
        "snapshot_bytes": output.stat().st_size,
        "snapshot_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "restored_integrity": verified["integrity"],
        "restored_tables": verified["tables"],
    }
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    receipt_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def restore_drill(snapshot: Path) -> dict:
    """Independently restore the snapshot into a disposable database."""
    if not snapshot.is_file():
        raise FileNotFoundError(snapshot)
    with tempfile.TemporaryDirectory(prefix="bean-sqlite-restore-") as folder:
        target_path = Path(folder) / "restored.sqlite"
        source = sqlite3.connect(
            f"file:{snapshot.resolve().as_posix()}?mode=ro", uri=True
        )
        target = sqlite3.connect(str(target_path))
        try:
            source.backup(target)
            target.commit()
        finally:
            source.close()
            target.close()
        return check_database(target_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="BEAN private SQLite backup and restore drill")
    actions = parser.add_subparsers(dest="action", required=True)
    save = actions.add_parser("backup")
    save.add_argument("--database", type=Path, required=True)
    save.add_argument("--out", type=Path, required=True)
    check = actions.add_parser("verify")
    check.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    result = (backup(args.database, args.out) if args.action == "backup"
              else restore_drill(args.database))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
