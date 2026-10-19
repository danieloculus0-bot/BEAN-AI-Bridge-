"""Read-only, local-only BEAN Operations pilot health diagnostics.

This reports counts and integrity results without revealing ERP rows, raw
identifiers or files to a server. It does not connect to external services.
"""
from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import sqlite3
import sys

from .backup import check_database, verify_backup
from .pilot import load_log, report as pilot_report


def inspect(*, database: Path | None = None, backup: Path | None = None,
            pilot: Path | None = None) -> dict:
    try:
        installed_version = version("bean-ai-bridge")
    except PackageNotFoundError:
        installed_version = "source-checkout"
    result = {
        "schema": "BEAN_OPERATIONS_HEALTH_V1",
        "mode": "OFFLINE_LOCAL_READ_ONLY",
        "python": ".".join(str(n) for n in sys.version_info[:3]),
        "version": installed_version,
        "database": {"state": "not_checked"},
        "backup": {"state": "not_checked"},
        "pilot": {"state": "not_checked"},
    }
    if database is not None:
        try:
            verified = check_database(database)
            conn = sqlite3.connect(
                f"file:{database.resolve().as_posix()}?mode=ro", uri=True
            )
            try:
                counts = conn.execute(
                    "SELECT kind, COUNT(*) FROM export_snapshots GROUP BY kind"
                ).fetchall()
                imported = conn.execute(
                    "SELECT COUNT(*), MAX(captured_at) FROM export_snapshots"
                ).fetchone()
                issues = conn.execute(
                    "SELECT COUNT(*) FROM import_issues"
                ).fetchone()[0]
            finally:
                conn.close()
            result["database"] = {
                "state": "pass", "integrity": verified["integrity"],
                "snapshot_count": imported[0],
                "latest_source_capture_utc": imported[1],
                "snapshot_kinds": {key: count for key, count in counts},
                "quarantined_rows": issues,
            }
        except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
            result["database"] = {
                "state": "fail", "problem": type(exc).__name__,
            }
    if backup is not None:
        try:
            checked = verify_backup(backup)
            result["backup"] = {
                "state": "pass",
                "receipt_verified": checked["receipt_verified"],
                "restore_integrity": checked["restored_integrity"],
                "snapshot_bytes": checked["snapshot_bytes"],
            }
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            result["backup"] = {
                "state": "fail", "problem": type(exc).__name__,
            }
    if pilot is not None:
        try:
            progress = pilot_report(load_log(pilot))
            result["pilot"] = {
                "state": "pass", "workdays_recorded": progress["workdays_recorded"],
                "pilot_complete": progress["pilot_complete"],
                "sites": progress["sites"],
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result["pilot"] = {
                "state": "fail", "problem": type(exc).__name__,
            }
    result["checks_requested"] = sum(
        arg is not None for arg in (database, backup, pilot)
    )
    result["all_requested_checks_pass"] = bool(
        result["checks_requested"] and
        all(v["state"] == "pass" for v in
            (result["database"], result["backup"], result["pilot"])
            if v["state"] != "not_checked")
    )
    result["production_certified"] = False
    result["note"] = (
        "Local structural checks only: not source authentication, "
        "commercial proof, disaster-recovery validation or production clearance."
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="BEAN Operations offline health diagnostics")
    parser.add_argument("--database", type=Path, help="Existing private export ledger")
    parser.add_argument("--backup", type=Path, help="Existing .sqlite backup and receipt")
    parser.add_argument("--pilot", type=Path, help="Existing private pilot.jsonl")
    args = parser.parse_args()
    print(json.dumps(inspect(database=args.database, backup=args.backup,
                             pilot=args.pilot), indent=2))


if __name__ == "__main__":
    main()
