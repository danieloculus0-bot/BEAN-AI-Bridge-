# EZ-BEAN / BEAN AI Bridge

**The thinking layer behind the ERP. Not the dashboard.**

EZ-BEAN is the planned company ERP-linked KPI development and operational reasoning framework. It reads authorized ERP information, normalizes and preserves evidence, calculates explainable KPIs, and identifies signals worth investigating. The future war-room visualization consumes its outputs; visualization is a separate application concern.

This repository is a **public-safe, generic implementation and smoke-test path** for that architecture. It has no live connection to company ERP systems and contains **synthetic data only**. It is **not** the ERP production connector, nor a deployed real-time dashboard.

## Part of the BEAN ecosystem

🌱 **[Meet BEAN on the live website](https://danieloculus0-bot.github.io/BEAN/)** · [Follow BEAN's development on GitHub](https://github.com/danieloculus0-bot/BEAN) · [Reproduce the offline quickstart](https://github.com/danieloculus0-bot/BEAN/blob/main/docs/GETTING_STARTED.md)

This repository is the **generic evidence, ERP reporting and replay integration layer**. For the persistent reasoning architecture, SQLite memory, uncertainty handling and review-required proposals, see **[BEAN Core](https://github.com/danieloculus0-bot/BEAN)**.

- [Start BEAN Core with an offline mock-provider demonstration](https://github.com/danieloculus0-bot/BEAN/blob/main/docs/GETTING_STARTED.md)
- [Evidence continuity contract between Core and Bridge](https://github.com/danieloculus0-bot/BEAN/blob/main/docs/EVIDENCE_BRIDGE_READINESS.md)
- [Published experimental findings and known limitations](https://github.com/danieloculus0-bot/BEAN/blob/main/docs/experimental-research-index-2026-10.md)

The Bridge's generic KPI functions and synthetic tests are distinct from BEAN's cognition modules. Links between projects do not imply that optional experimental branches have been merged or production integrations deployed.

## Executed growth learning (synthetic Lab010)

The [Growth Learning Bridge lab](experiments/growth_bridge/README.md) uses real online reward updates rather than recording recommended strategies without executing them. Across 300 training episodes the policy learns from simulated portfolio returns, **chooses and executes** long-or-cash exposure from five competing strategies, stores its reward-trained policy, reloads that checkpoint, and grades 100 never-trained mock market seeds against both untrained BEAN and the strongest fixed rule. The executed action ledger, modeled fees and independent Windows/Linux acceptance receipts are preserved.

**Reproduced mock benchmark:** trained +33.43% mean synthetic bankroll return; unchanged untrained policy +4.75%; strongest fixed rule +11.43% (all over the same 100 synthetic trials). The paired bootstrap 95% improvement interval against the strongest fixed baseline was +18.41 to +25.70 percentage points. [See the passing dual-platform run](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38225147021).

These artificial worlds are deliberately easy. These results do **not** imply profit, real-market generalization, an independently improved learning algorithm, a BEAN Core promotion, or an AIscend live trading change. The module has no wallet or exchange access.

## Evidence learning loop (opt-in)

The [EvidenceLearningLoop](experiments/learning_loop/README.md) is a reusable, provider-agnostic component that routes rejected or stale model answers to a separately supplied investigator and evidence verifier. It requires corroboration from **at least two distinct verified provenance origins** before creating a new versioned definition, retains conflicting and inconclusive cases, and writes bounded durable cycle records to SQLite.

Import: `from ezbean import EvidenceLearningLoop, SourceObservation`.

**Boundaries:** the host must independently authenticate and authorize its verifier; mere source IDs are not evidence of truth. This module neither modifies LLM weights nor runs unattended, performs external actions, or touches production ERP data. The BEAN Core audit journal is an optional local integration when Core is installed. The bundled experiment uses synthetic examples; see the [cross-platform tests](tests/test_learning_loop_lab009.py).

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

## Current generic proof of concept

- ERP observation normalization via a common adapter interface.
- Read-only offline fixture adapter using fictional records.
- Append-only SQLite observation ledger with idempotent ingestion and conflict detection.
- Deterministic, as-of timestamp replay, including corrected observations.
- Job-based OTD, completed shipments, past-due open jobs, RMA counts/quantity/cost, good/scrap quantities and scrap rate.
- Evidence references attached to every KPI, and rules that flag signals without inventing root causes.
- Cross-platform Python smoke tests on actual Windows and Linux GitHub Actions runners.

**Scope warning:** Initial OTD definition assumes one completed shipping date per job. Partial shipments, customer-requested-versus-promised dates, credits, RMA costing, cancellations, and official business rules require explicit ERP mapping and approval before production reporting. A missing denominator is N/A rather than 0%.

## Daily Exception Brief (opt-in, local)

BEAN can now turn an existing **private JobBOSS export ledger** into a one-page [Daily Exception Brief](docs/DAILY_EXCEPTION_BRIEF.md), with shipment-line OTD, verified/unknown state, past-due job-line evidence, RMA uncertainty and a prioritized source gap-resolution queue. Run a current report against an earlier cutoff for same-period evidence changes, without exposing raw source identities or treating unknown data as zero.

```bash
PYTHONPATH=src python -m ezbean.daily_brief --database ./private/site.sqlite --site SITE_A --start 2026-10-01 --as-of 2026-10-10T12:00:00Z --out ./private/morning.html
```

This is a **read-only offline report**, not an authorized ERP integration, notifications service, or official OTD scorecard. Local files and outputs must stay outside public GitHub repositories. Tests use synthetic data and explicitly check incorrect/unknown cases.

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
## Optional JobBOSS export reporting module

The generic Bridge includes a separate **offline JobBOSS export sponge**, which imports explicitly supplied Job Schedule and Shipment Summary CSV files and an RMA Tracker workbook to an append-only local SQLite evidence database. It preserves source row lineage and historical corrections, reports shipment-line OTD separately from the older job-completion KPI, and uses **unknown/N/A instead of fabricating zeros** when necessary source coverage is absent. A deterministic management report can compare like-for-like verified measures across sites without inventing a peer value, and strips raw source identifiers from its aggregate report. This is an optional, local-only adapter using synthetic data in CI, **not an authenticated live ERP connection or official OTD scorecard**. The source spreadsheets, local ledger, HTML and JSON outputs must remain outside this public repository. See [the JobBOSS export protocol and limitations](docs/JOBBOSS_SPREADSHEET_SPONGE.md).

## Optional versioned definition and output gate

The Bridge also provides a **deterministic, local-first versioned definition library** and `OutputGate` that validates a provider's proposed answer against a current, explicitly supplied definition revision. It rejects fabricated reference IDs, stale or retracted definitions, and mismatched canonical values, and abstains when the record is unavailable. Historical as-of lookups remain available. Tests use a fake local provider; **no hosted-model success, independent source authentication, or automatic fact discovery is implied**. External evidence references are assertions supplied by the host and must be verified separately. This optional interface does not globally intercept BEAN's reasoning engine or ERP arithmetic. See [versioned output contract](docs/LAB008_DYNAMIC_DEFINITIONS.md).

## Generic ledger reliability contract

Raw generic normalized KPI events now require an explicit, versioned completeness assertion before an otherwise unobserved count is displayed as zero. Missing data remains `null`/N/A, and batch ingestion is atomic on all-or-nothing conflicts. Source completeness is **asserted by an adapter**, not independently authenticated. The separate JobBOSS reporting adapter has its own coverage and KPI semantics. See [ERP source completeness and transaction contract](docs/ERP_RELIABILITY_CONTRACT.md).

## Robot Motion (experimental)

The [Robot Motion Emulator Lab](experiments/robot_motion/README.md) runs a shared motor interlock under native C, Arduino Nano/ATmega328P simavr, and ESP32 QEMU, with an optional token-gated ESP32 Wokwi lane. It uses synthetic test vectors, never drives robot hardware, and records separate emulator evidence. This is distinct from BEAN Core's simulated joint-state motion layer and from production motor control.
