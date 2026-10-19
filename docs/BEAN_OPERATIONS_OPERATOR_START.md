# BEAN Operations — one-page pilot operator guide

**October 19, 2026 · Local technical beta · No paid customer claims**

This guide is for the **BEAN Operations** read-only evidence/reporting pilot.
The separately developed BEAN Core cognition system remains experimental.
This beta makes no live ERP API connection, does not email anyone, and does
not transmit source data to GitHub.

## 1. Install from the tested GitHub Actions beta wheel (offline)

Download the build artifact for Windows or Linux from the
[readiness workflow](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/workflows/bean-five-readiness.yml).
Extract the `.whl` file to a folder on the test PC, for example
`C:\BEAN-Install\`. Download the accompanying
`scripts/install_beta.py` from the same commit.

With Python 3.11 or 3.12 installed, on Windows PowerShell:

```powershell
python .\scripts\install_beta.py --wheel "C:\BEAN-Install\bean_ai_bridge-0.1.0b2-py3-none-any.whl" --home "$env:LOCALAPPDATA\BEAN-Operations"
```

Use the **actual downloaded filename** if it differs from this example.
Installation is from a local wheel with `--no-index` and has no Python
package-download requirement. It creates an isolated venv and **fictional**
demo inputs in the chosen private workspace. The generated HTML clearly
says it is fictional.

## 2. Run one real local, authorized export report

Arrange authorized Job Schedule, Shipment Summary, and RMA Tracker exports
in a private folder on the pilot PC, outside the public GitHub checkout.
Reason codes in the RMA tracker are optional. Run:

```powershell
& "$env:LOCALAPPDATA\BEAN-Operations\.venv\Scripts\bean-run.exe" `
  --exports "C:\Private\BEAN\Exports" `
  --database "C:\Private\BEAN\site.sqlite" `
  --start "2026-10-01" `
  --as-of "2026-10-19T12:00:00Z" `
  --site "SITE_A" `
  --out "C:\Private\BEAN\daily.html"
```

Replace the timestamp and period with the **actual authorized source capture
time** and the intended reporting window; the above is illustrative.

The command imports recognized exports, checks structural data, writes the
local SQLite ledger, produces `daily.html`, `daily.json`, and
`daily.receipt.json`, and prints a machine-readable run receipt. Import
receipts contain file hashes and aggregate results, not a claim that BEAN
authenticated the ERP. A file with an invalid schema causes an explicit
error rather than issuing a misleading new report.

## 3. Health, recovery and evidence

```powershell
& "$env:LOCALAPPDATA\BEAN-Operations\.venv\Scripts\bean-backup.exe" backup `
  --database "C:\Private\BEAN\site.sqlite" `
  --out "C:\Private\BEAN-Backups\site-20261019.sqlite"

& "$env:LOCALAPPDATA\BEAN-Operations\.venv\Scripts\bean-doctor.exe" `
  --database "C:\Private\BEAN\site.sqlite" `
  --backup "C:\Private\BEAN-Backups\site-20261019.sqlite"
```

`bean-doctor` reports local integrity, import counts, snapshot timestamps,
quarantine counts and whether the backup's sidecar SHA256 receipt agrees
with an independently restored database. It does **not** display raw customer,
job or operator rows. A green health report does not establish independent
source authentication or enterprise disaster recovery.

## 4. Real ten-workday evidence collection

Follow [the original pilot guide](OPERATIONAL_PILOT_RELEASE.md) and record
each day's manually timed baseline review, BEAN-assisted review, confirmed
useful findings, false alerts, and missed issues using `bean-pilot`.
Keep records **private**; do not upload real business exports to public GitHub.

Success requires external observations, not completed fictional tests.
Record what doesn't work. Before claiming results, the source
metric definitions and trial method should be agreed with the pilot site.

## What the beta provides and what it still doesn't

**Provides:** a locally installable beta; one-command import/report;
private SQLite lineage; idempotent duplicate imports; receipt hashing;
readable exception brief; local health checks; backup/restore drill;
pilot value measurement; Linux/Windows test evidence.

**Not yet proven:** authenticated live ERP integration, official customer OTD
definitions, field reliability with real operators, robust off-device
disaster recovery, customer willingness to pay, commercial licensing,
support contracts, updates or independent production security assessment.

BEAN Core's experimental cognition is **not** restrained, deployed or
modified by the operational pilot.
