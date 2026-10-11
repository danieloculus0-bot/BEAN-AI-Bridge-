# BEAN Daily Exception Brief — local, read-only pilot

**Purpose:** turn the existing JobBOSS export ledger into a one-screen daily review of shipment-line OTD, overdue job-line evidence, RMA occurrence uncertainty and actionable missing-data exceptions. The source calculation is deterministic, with *no LLM*, no external network connection, no company-specific mappings and no emails.

The public repository contains only code and fictional test fixtures; use a separately protected private directory for real exports, ledgers and outputs.

## One local command after import

The [JobBOSS export sponge](JOBBOSS_SPREADSHEET_SPONGE.md) must have ingested your manually authorized Job Schedule, Shipment Summary and/or RMA Tracker exports into **an existing private SQLite ledger**. This command reads that ledger (it does not automatically export from ERP):

**PowerShell:**

\`\`\`powershell
$env:PYTHONPATH = "src"
python -m ezbean.jobboss_exports --database "C:\private\bean\site.sqlite" scan "C:\private\exports"
python -m ezbean.daily_brief --database "C:\private\bean\site.sqlite" --site SITE_A --start 2026-10-01 --as-of 2026-10-10T12:00:00Z --previous-as-of 2026-10-09T12:00:00Z --out "C:\private\bean\morning.html"
\`\`\`

**Linux/macOS:**

\`\`\`bash
PYTHONPATH=src python -m ezbean.daily_brief --database ./private/site.sqlite --site SITE_A --start 2026-10-01 --as-of 2026-10-10T12:00:00Z --previous-as-of 2026-10-09T12:00:00Z --out ./private/morning.html
\`\`\`

Omit \`--previous-as-of\` for the first run. The timestamps must include explicit timezones; the optional previous cutoff must be earlier than the current cutoff and use the same reporting period. For real use, replace these examples with the **actual known export cutoff timestamps** and keep the start date consistent. The command produces \`morning.html\` and \`morning.json\` locally. Do not check the outputs or SQLite database into a public repo.

## How to read the output

- **Source-checked metrics** display their value and evidence state. OTD is a percentage *per shipped report line*, not an official customer promise-date scorecard. Source-provided data and coverage are not independently authenticated.
- A **missing, conflicting or unverified** metric displays N/A, not a confident zero or percentage. If malformed RMA dates are quarantined, its observed count is labeled **at least N** instead of a true total.
- **Review queue** orders explicit source quality gaps: P0 for absent core exports, ambiguous job shipped quantities, shipment-date conflicts and quarantined RMA dates; P1 for follow-up verification and policy definition; P2 for unavailable quantity/cost fields. These are **suggested evidence checks**, not automatically assigned CARs, root causes or action approvals.
- **Changes since an earlier cutoff** show only comparable, source-checked numeric snapshots. It never subtracts N/A or suggests a before/after change proves increased performance. The gap queue separately identifies newly found and resolved evidence gaps.
- **Privacy:** output includes only allowlisted aggregate numbers, status and general instructions; raw ERP row IDs, customer names, descriptions, filenames and source record references remain in the local ledger, outside the management brief.

The file is intentionally *not* a scheduled daemon or substitute for authorized source review. Additional future work includes reconciling official business-specific definitions, verifying actual time savings and incorporating a human-approved RMA/CAR owner and due-date list.

## Reproduce the public tests

\`\`\`bash
PYTHONPATH=src python -m unittest discover -s tests -p test_daily_brief.py -v
\`\`\`

The tests use fictional data and an empty real SQLite ledger. They challenge N/A semantics, contradictory dates, RMA quarantine, privacy redaction, source cutoff ordering, and idempotent reproducibility on Windows and Linux.

This addresses the P0 [day-to-day usefulness audit](https://github.com/danieloculus0-bot/BEAN/blob/main/docs/BEAN_DAY_TO_DAY_USEFULNESS_AUDIT_2026-10-10.md) without claiming deployment into EZ Fab or externally verified intelligence.
