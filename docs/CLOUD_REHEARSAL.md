# BEAN cloud rehearsal: from built wheel to a reproducible pilot dry run

**October 19, 2026** — development / software-verification experiment.

This experiment uses **GitHub Actions cloud compute** to build and install the
actual `bean-ai-bridge` beta wheel and execute a full fictional operational
scenario. It is **not** a live customer deployment, model cognition benchmark,
paid-customer validation or evidence of genuine workplace time savings.

## Reproduce the experiment

On a clean Python 3.11/3.12 environment (Windows or Linux), from this branch:

```bash
python -m pip install .
python -m experiments.cloud_operations_rehearsal.run --out cloud-rehearsal-evidence
python -m unittest discover -s tests -p test_cloud_rehearsal.py -v
```

The Actions workflow is `BEAN cloud operations experiment`
(`.github/workflows/bean-cloud-cook.yml`).

The workflow builds a **wheel** and installs that wheel. Each job then runs
the scenario twice from independent temporary directories and independently
verifies the existing pilot/backups tests.

## What the fictional scenario actually executes

- 10 separate working days of fictional Job Schedule and Shipment Summary
  CSV snapshots, and two fictional RMA Tracker XLSX snapshots.
- Actual JobBOSS export ingestion and SQLite append-only evidence records,
  including source timestamp/correction logic.
- A deliberately wrong `DaysEarlyLate` field on one fictional shipment
  snapshot: the derived OTD state must become `CONFLICTED`, then recover to
  `VERIFIED` following the corrected source snapshot.
- An RMA tracker that **omits the Reason Code column** completely. Valid
  dated returns remain counted and the missing code never creates an issue.
- A later RMA tracker with a malformed date; its rows are quarantined and
  valid dated RMA counts become a known **lower bound**, not a fabricated
  total.
- 10 deterministic daily briefs, each compared with the previous cutoff.
- 10 hash-linked trial entries with **invented** review durations and
  **invented** reviewer assessments.
- Midpoint online SQLite backup, SHA256 receipt comparison, restore drill,
  then a separate restored source-ledger check.
- Two full independent replay runs, compared using a deterministic SHA256
  of the sanitized outputs (not the transient database files).

## Evidence available as GitHub workflow artifacts

Each of the four platform/version jobs uploads a short-lived, **explicitly
fictional** artifact. It contains:

- `synthetic_rehearsal.json`: replay hash, reliability observations and
  fictional aggregate trial metrics.
- `synthetic_pilot.html`: labeled illustrative pilot view.
- `synthetic_last_brief.html`: labeled illustrative daily operational brief.
- One built beta wheel.

Artifacts are retained for 14 days. No real site exports, customer records,
ChatGPT conversations, or proprietary data are pushed to this repository or
to the artifacts.

### How to interpret the results

The output deliberately sets:

- `synthetic = true`
- `real_customer_pilot = false`
- `production_readiness_verified = false`
- `commercial_value_verified = false`

The embedded pilot report may say `pilot_complete=true` because its ten
**fictional** workday entries were created. This refers only to test
coverage, **not to completion of the separate real-world customer pilot**.
Treat synthetic time savings, false alerts, and reviewer assessments as
fixture values, never achieved performance.

## Fixed in this branch

The backup `verify` command now checks the original sidecar receipt,
snapshot filename, byte length, SHA256 and independently restored tables.
Previously it performed an integrity/restore drill without confirming
the restored file matched the snapshot named in the receipt. Regression
tests cover missing and mismatched receipts.

The SHA256 receipt is not an independently signed attestation and does not
establish offsite disaster recovery. Encryption, custody, external retention,
authenticated source access, real operator workflow, support and pricing
remain tasks for a genuine production/commercial readiness evaluation.

## Readiness boundary

**Engineering progress:** installable artifact, tested four cloud runners,
reproducible 10-day application exercise, historical-correction behavior,
backup receipt check and a contained set of synthetic failure scenarios.

**Unproven:** live ERP source legitimacy and semantic definitions; a real
10-workday pilot; useful correct/incorrect issue detection relative to humans;
actual user productivity gain; reliable off-host restore; licensing,
commercial agreements and recurring customer demand.

These experiments do not change BEAN Core's cognitive behavior, do not add
behavioral restrictions, and do not modify the public website.
