# BEAN Operations — private pilot release candidate

**Date:** 2026-10-19  
**Status:** Technical beta / local-only pilot candidate; **not** a production
release, ERP connection, certified evidence source, or commercial license.

The operational pilot is a **separate product-development track** from BEAN Core
cognitive experimentation. The Bridge remains the shared logic-module bus.

## Installation

This experimental branch packages the existing offline Bridge commands.
Use a dedicated Python 3.10+ environment and a checkout of
`feature/operational-pilot-readiness-20261019`.

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\bean-export.exe --database "C:\private\bean\site.sqlite" scan "C:\private\exports"
.\.venv\Scripts\bean-brief.exe --database "C:\private\bean\site.sqlite" --site SITE_A --start 2026-10-01 --as-of 2026-10-19T12:00:00Z --out "C:\private\bean\day01.html"
```

Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/bean-export --database ./private/site.sqlite scan ./private/exports
.venv/bin/bean-brief --database ./private/site.sqlite --site SITE_A --start 2026-10-01 --as-of 2026-10-19T12:00:00Z --out ./private/day01.html
```

The ERP exports must have been supplied manually or through a separately
authorized process; running this package does not authenticate to the ERP.
Example dates are illustrative, not current live source cutoffs.

## 10-workday comparative value pilot

Run one authorized operational review per workday, on a **matching source
snapshot**, twice: once using the current manual review process and once with
the BEAN-assisted brief. Use the same scope; ideally alternate review order
and record material differences. Before seeing performance results, define
what counts as a useful caught exception, false alert, and missed issue. A
reviewer, not BEAN, adjudicates outcomes.

After generating each daily brief, append the day's measurements:

```powershell
.\.venv\Scripts\bean-pilot.exe record --log "C:\private\bean\pilot.jsonl" --brief "C:\private\bean\day01.json" --day 2026-10-19 --baseline-minutes 30 --bean-minutes 18 --confirmed-useful 2 --false-alerts 1 --missed-issues 0
```

- `baseline-minutes`: observed conventional process review time for same work.
- `bean-minutes`: observed BEAN-assisted review and confirmation time,
  **including** time spent investigating misleading output.
- `confirmed-useful`: machine-presented exceptions independently confirmed
  worth investigating.
- `false-alerts`: presented exceptions judged unsupported or non-actionable.
- `missed-issues`: relevant items the reviewer found but the BEAN review missed.

Other presented exceptions can remain unadjudicated, not automatically true.
The log retains **only these aggregates**, an anonymous site code, the
brief's SHA256, date and cutoff; never enter real customer names, identifiers
or comments in the public repo. Each entry links to its predecessor. Duplicate
site/day updates are rejected; do not silently rewrite experimental history.

After ten distinct workdays for a single site:

```powershell
.\.venv\Scripts\bean-pilot.exe report --log "C:\private\bean\pilot.jsonl" --site SITE_A --out "C:\private\bean\pilot-summary.html"
```

The output includes actual time difference, confirmed findings, false alerts,
missed issues, source receipt references and a clear `pilot_complete` flag.
**No day is invented when the ledger is empty.** Ten days are a minimum
observation window, not proof of return on investment or independent customer
demand. Repeat at an external test site before assuming generalization.

## Backups and restore drills

Use SQLite's online backup API, not `copy` of an open WAL database.

```powershell
.\.venv\Scripts\bean-backup.exe backup --database "C:\private\bean\site.sqlite" --out "C:\private\backups\site-20261019.sqlite"
.\.venv\Scripts\bean-backup.exe verify --database "C:\private\backups\site-20261019.sqlite"
```

Backup creation produces a local `.receipt.json` with checksum, table listing
and the outcome of a restore into a **temporary, independent** SQLite file.
No external data is transmitted; the backup contains actual sensitive source
data if the source ledger did. Keep backups in private controlled storage.
This is a **restore drill**, not evidence of off-host disaster recovery,
access-control validation, encryption, or managed retention.

## Pilot acceptance evidence to gather

| Dimension | Evidence needed before a production-readiness increase |
| --- | --- |
| Functionality | Site-specific report definitions reconciled to the source ERP and signed off by the local owner |
| Accuracy | Ten recorded workdays with independently confirmed findings, false positives and missed issues |
| Value | Comparable manual vs BEAN time logs and an actual user willing to repeat/pay; record failed trials too |
| Reliability | Successful install, export replay, data correction/reimport and restart on representative Windows PCs |
| Recovery | Backups with verified off-device restore, simulated data-loss test and documented RTO/RPO |
| Data controls | Verified approved source credentials/scope, operator access, encryption, retention and audit handling |
| Product terms | Owner-selected license, user agreement, pricing/support commitment and maintenance/version policy |

These are requirements for **claiming** commercial/production readiness, not
new restrictions on Core's virtual-environment thought experiments. BEAN can
keep experimenting and building cognitive layers independently.

## Known deficits

- No authenticated ERP API connector, enterprise identity/access integration,
  encryption/key management, managed deployment/updates or commercial terms.
- No observed external customer pilot or established willingness to pay.
- SQLite SHA receipts are useful for continuity; without separate custody,
  full-file replacement/tampering is outside their proof scope.
- RMA reason codes are optional; missing codes do **not** create a reportable
  issue and dated occurrences still count. Issue themes are populated only
  when supported by existing descriptions.
- Generic shipment-line OTD is **not** automatically a customer's approved
  definition. Company-specific reporting semantics remain site-configured.

## Verification

Run:

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p 'test_pilot.py' -v
python -m unittest discover -s tests -p 'test_backup.py' -v
```

The GitHub pilot workflow tests the install, CLI entry points, full existing
regressions and receipt/recovery behavior on Windows and Linux.
