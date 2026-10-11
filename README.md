# EZ-BEAN / BEAN AI Bridge

**The thinking layer behind the ERP. Not the dashboard.**

EZ-BEAN is the planned EZ Fabricating ERP-linked KPI development and operational reasoning framework. It reads authorized ERP information, normalizes and preserves evidence, calculates explainable KPIs, and identifies signals worth investigating. The future war-room visualization consumes its outputs; visualization is a separate application concern.

This repository is a **public-safe, generic implementation and smoke-test path** for that architecture. It has no live connection to EZ Fab ERP systems and contains **synthetic data only**. It is **not** the ERP production connector, nor a deployed real-time dashboard.

## Architecture

```
ERP (authorized read-only adapter)
   |  observations / source IDs / timestamps
   v
Generic integration contract / validation
   |
   v
Append-only event ledger (SQLite) + deterministic replay
   |
   +-- deterministic KPI calculators (never LLM arithmetic)
   |
   +-- evidence-backed thinking module (rules now; BEAN integration later)
   |
   v
Versioned reporting data contract / audit trace
   |
   v
War-room display (a separate future client)
```

This project intentionally has **no dependency on 64Δ**. It is an independent ERP/KPI logic engine.


## JobBOSS spreadsheet sponge (experimental)

The [JobBOSS spreadsheet sponge](docs/JOBBOSS_SPREADSHEET_SPONGE.md) is a local-only, read-only import path for existing Job Schedule CSV, Shipment Summary CSV, and RMA Tracker XLSX files. It captures immutable source snapshots in a local SQLite database, generates shipment-line OTD and overdue job-line metrics, preserves row evidence, and reports RMA counts without inventing missing quantity or costs. No live ERP connection or customer data is committed here. Windows/Linux tests use synthetic fixtures; this is not yet an authoritative production OTD scorecard.

## Current generic proof of concept

- ERP observation normalization via a common adapter interface.
- Read-only offline fixture adapter using fictional records.
- Append-only SQLite observation ledger with idempotent ingestion and conflict detection.
- Deterministic, as-of timestamp replay, including corrected observations.
- Job-based OTD, completed shipments, past-due open jobs, RMA counts/quantity/cost, good/scrap quantities and scrap rate.
- Evidence references attached to every KPI, and rules that flag signals without inventing root causes.
- Cross-platform Python smoke tests on actual Windows and Linux GitHub Actions runners.

**Scope warning:** Initial OTD definition assumes one completed shipping date per job. Partial shipments, customer-requested-versus-promised dates, credits, RMA costing, cancellations, and official business rules require explicit ERP mapping and approval before production reporting. A missing denominator is N/A rather than 0%.

## Local smoke-test path

Python 3.11+; standard library only:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m ezbean.demo
```

PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -v
python -m ezbean.demo
```

The demonstration prints `SYNTHETIC_TEST`; results cannot be mistaken for live company KPIs. GitHub Actions runs identical tests on `ubuntu-latest` and `windows-latest`.

## Layer ownership

- **BEAN core:** durable cognition, evidence, uncertainty, hypothesis handling (separate project).
- **Generic bridge (here):** ERP adapter contract, evidence ledger, replay, KPI calculation, test harness.
- **EZ-BEAN:** site-specific ERP semantics, thresholds, diagnostic reasoning policies, and configurable KPI definitions. These are not embedded with proprietary site data in this public repository.
- **War room:** an independently deployable operational visualization, fed by EZ-BEAN reports.

## Production gates (not implemented)

Secure ERP authentication, incremental ingestion, schema/version governance, reconciliation to authoritative ERP reports, source permission boundaries, privacy and retention controls, data-freshness alarms, audit-approved KPI definitions, near-real-time processing, and integration with the BEAN reasoning core. These must be implemented and validated before calling the system production-ready.