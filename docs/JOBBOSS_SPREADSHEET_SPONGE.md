# BEAN JobBOSS Spreadsheet Sponge

**Prototype: local, read-only, export-driven input adapter.**

This lives in the **BEAN-AI-Bridge-** repository. It does not create a separate ERP, overwrite JobBOSS records, scrape authenticated websites, or require an ERP API. Applications such as ForgeQC, MFGForge/SuperForge, Axiom, and EZ Expedite may eventually consume its versioned output.

## Recognized inputs

- **Job Schedule — Detail Report.csv:** the existing JobBOSS report with columns including `JobNumber`, `QtyOrdered`, `DueDate`, `QtyShipped`, and `ShippedDate`. Used as a point-in-time snapshot for overdue open **job lines**.
- **Shipment Summary — Detail Report.csv:** the existing report with `PackingList`, `OrderNumber`, `JobNumber`, `DateShipped`, `DueDate`, `QtyShipped`. Used to calculate on-time delivery **per shipped report line**, not per completed job or by a separate customer scorecard definition.
- **RMA_Tracker(...).xlsx:** the existing `RMA Log` worksheet, with `Date`, `Order Number`, `Customer`, `Department`, `Person`, `Defect Description`, `Reason Code`. Its dated occurrences can produce counts and reason-code summaries. This is an existing tracker workbook, not necessarily a native JobBOSS RMA export.

**Missing measures are unknown, not zero.** The RMA tracker does not supply trustworthy `quantity` and `cost` columns, so this adapter leaves RMA quantity and dollar values **null**. Blank RMA reason codes are counted explicitly as `rma_missing_reason_entries`, rather than silently disappearing from the quality distribution. Malformed RMA dates are quarantined by source row reference and excluded from the period count while retaining the rest of the workbook. This behavior handles a date-format defect found during inspection of an existing tracker export without rewriting its source. The distinct `NCRRMA.xlsx` report has a different schema and includes WorkOrder/PurchaseOrder/Item/SalesOrder records; it must not be conflated with a customer RMA count without an explicit classification rule.

## Operation

Drop newly exported spreadsheets into a local input folder. You may import once or poll it while BEAN is running.

```powershell
$env:PYTHONPATH = "src"

# One batch
python -m ezbean.jobboss_exports --database .\site_data\jobboss.sqlite scan "C:\JobBOSS Exports"

# Or watch for updated files every 10 seconds
python -m ezbean.jobboss_exports --database .\site_data\jobboss.sqlite watch "C:\JobBOSS Exports" --interval 10

# Generate versioned output JSON from ingested exports
python -m ezbean.jobboss_exports --database .\site_data\jobboss.sqlite report --start 2026-09-01 --as-of 2026-10-01T18:00:00Z --out .\site_data\jobboss_output.json
```

Manual import supports explicitly supplying a capture timestamp when a file has been renamed:

```powershell
python -m ezbean.jobboss_exports --database .\site_data\jobboss.sqlite import --captured-at 2026-10-01T14:00:00Z "C:\Exports\renamed.csv"
```

Unmodified ECI-style report filenames contain their capture time. When the filename does not, the program refuses to **guess** and requires `--captured-at`. Every unique file SHA-256 is stored once in local SQLite along with its source row numbers and snapshot timestamp. Replaying an unchanged export does not double count it. Later job schedules supersede earlier snapshots; shipment lines are accumulated across exports with a stable shipment identity, applying later corrections to the same identity.

The exported JSON contains metric values, source coverage, evidence row references, and clear limitations. The source spreadsheets and local SQLite database must stay **outside** the public repository. The GitHub tests use synthetic fixture rows only.

## Semantics and audit boundaries

The pilot's OTD denominator is one record per shipped JobBOSS Shipment Summary line. A packing list containing several job lines contributes several records. Partial shipment policy, split delivery reconciliation, customer promise-date changes, cancellations, and official customer scorecard business rules require explicit policy before calling this an authoritative OTD calculation.

A job line is considered overdue in the latest Job Schedule snapshot when its due date precedes the report as-of date and `QtyOrdered > QtyShipped`. This is **not** proof of the customer's requested promise date, and cannot reproduce historical schedule changes before the first captured snapshot.

**RMA count** represents dated rows from the latest `RMA Log` worksheet. It does not imply unique customer return authorizations unless that workbook has such a key and duplicates are reconciled.

Imports and derived outputs are separate from any source-of-truth JobBOSS application. The engine does not invent root causes, adjust the ERP, or claim real-time coverage between exports. A 10-second folder poll only detects **new export files**; it cannot see changed ERP records until someone or an approved process exports them.

## Existing repository roles

- `BEAN`: persistent reasoning and provenance core.
- `BEAN-AI-Bridge-`: source ingest, snapshots, normalized evidence and KPI outputs (this adapter).
- `MFGForge`: canonical SuperForge suite source.
- `SuperForge_Unofficial`: packaged release candidates; not primary implementation.
- `ForgeQC`: quality operations and an existing RMA Excel import.
- `EZ_Expedite`: corrective occurrences and RMA action routing.
- `Axiom_Beta`: consolidated application including ERP/quality components.
- `ForgeVault`: controlled documents and revision vault.
- `EZ-FAIR`: first-article inspection and drawing balloons.
- `PM-Tracker`: maintenance workflow.
- `64-`: operational causal/organization prototype.
- `venvWin`: portable Windows compatibility environment.
- `AIscend`: autonomous trading experiment (outside manufacturing/ERP scope).

This is a **shared bridge output contract**, not a parallel replacement for SuperForge or Axiom.

## Private executive intelligence (optional, no email)

The bridge contains a deterministic, auditable **BEAN management intelligence** layer for an optional site-to-site comparison. It never guesses that a source-export site is better. Only **the same metric, exact same reporting dates, and fully reconciled field logic** can be compared. If peer records are not supplied, the peer stays **N/A**, no difference/winner is calculated. The system exposes unresolved data gaps and can mark a missing/contradictory value as **CORRECTED** when new evidence supports it, without rewriting the old snapshot.

The **Job Schedule shipped-quantity column is sometimes blank in real exports**. In that case, past-due *open-job* counts are no longer asserted; an independent count of past due-date schedule lines is retained and the open classification stays unknown. Shipment quantities such as \`1,250\` are normalized exactly (no floating-point approximation), and JobBOSS's own \`DaysEarlyLate\` is checked against shipped minus due day for each line. This establishes fidelity to the **shipment-line** date calculation but does not imply agreement with every official OTD business policy.

From the repository root, with site-specific ledgers already imported locally:

\`\`\`powershell
$env:PYTHONPATH = "src"
python -m ezbean.management_intelligence --primary-db .\site_data\primary.sqlite --primary-site SITE_A --start 2026-09-01 --as-of 2026-10-01T18:00:00Z --output .\site_data\private_management.html
\`\`\`

Add \`--peer-db .\site_data\peer.sqlite --peer-site SITE_B\` only after obtaining an equally structured and validated peer dataset. The offline HTML and companion JSON contain **only aggregate numbers, evidence-state labels, and gap prompts**. Raw IDs, customer names, defect descriptions, and source paths stay in the site's private ledger; the report intentionally strips them. The optional \`--note-file\` argument can insert a private human-authored management message (escaped as plain text). **The tool never sends mail or posts data to a network.** Keep the generated HTML and JSON outside a public repository and review them before forwarding.

This is the BEAN Bridge's **rules-based reasoning stage**, not a claim that neural BEAN Core or Ollama independently validated facts. Future BEAN Core integration must retain deterministic KPI math and evidence gates.

