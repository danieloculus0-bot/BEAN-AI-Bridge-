# ERP reliability contract: explicit unknowns, source coverage and atomic import

## Why

A source export that contains no RMA rows does not prove zero RMAs happened. Likewise, a filtered Job Schedule cannot prove zero past-due jobs. An import that fails halfway through cannot leave the first half committed as though it was a completed snapshot.

## Current behavior

- Without category observations or qualifying completeness assertions, count/total outputs for unobserved groups are **null / N/A**. This includes no observed shipments, RMAs, production and overdue jobs.
- Observed positive counts and recorded sums remain available, but are explicitly **observed-only** when source coverage is unknown. An observed source row with a literal zero quantity remains zero for that row.
- A normalizing source may provide \`source_coverage\` observations. These are **source claims**, not independent source authentication. The output distinguishes \`ASSERTED_COMPLETE\` from \`UNKNOWN\`; the exact assertion evidence ID is retained for explicit zeros. A later validator should authenticate source authority and reconcile the source report totals.
- Report \`schema_version\` is \`0.2\`, adding the \`source_coverage\` object; original KPI keys and object fields remain. Downstream consumers must not assume zero from a null value.
- Generic \`Ledger.ingest_all()\` is a **single SQLite transaction**. A conflicting identity, bad JSON or a generator exception rolls back the entire batch while preserving previously committed events. Single-record ingest remains atomic and idempotent.
- The thinking module explicitly reports incomplete sources as N/A, rather than quietly coercing null to a zero.

## Completeness assertion fixture

The following is a fictional source claim and should only be accepted from an authorized local normalization adapter, not from an untrusted model or prompt.

\`\`\`json
{
  "source": "synthetic_report_A",
  "event_id": "snapshot-rma-coverage-20261008",
  "entity_type": "source_coverage",
  "entity_id": "RMA_SNAPSHOT",
  "observed_at": "2026-10-08T16:00:00+00:00",
  "payload": {
    "domain": "rma",
    "window_start": "2026-10-01",
    "through": "2026-10-08T16:00:00+00:00",
    "complete": true,
    "scope": "reporting_window"
  }
}
\`\`\`

Supported domains: \`job\` (scope \`full_snapshot\` including all open jobs), \`rma\` and \`production\` (scope \`reporting_window\`). \`through\` must exactly match the report cutoff, \`window_start\` must cover the report start, and claims must match every observed source for the domain. A report with **no observed records** can accept an explicit zero only when a matching completeness assertion exists. Future-dated and stale assertions cannot certify earlier or later periods. True zero denominators still produce N/A for rate/percent KPIs.

**Important:** An apparently valid completeness assertion can still be fabricated or supplied by a misconfigured importer. This stage enforces a declaration contract, not cryptographic verification. A production host must authorize which sources may declare completeness and reconcile row/total counts with the original ERP report. Source capture time and report semantics must be standardized before trusting cross-site output.

## Recovery test plan

- Empty ledger ⇒ N/A counts and rates, visible unknown-source findings.
- Source rows without completeness ⇒ observed-only positives and totals, but no invented zero count.
- Coverage-only snapshot ⇒ zeros with source reference, rates N/A when denominator 0.
- Wrong scope, incomplete, mismatched timestamp, future assertion and mixed source declarations ⇒ no zero certification.
- Late conflicting event or iterator failure ⇒ no partial batch remains in SQLite, including across restart.
- Existing RMA/OTD fixture and all JobBOSS offline import/management tests remain passing.

Run locally with \`PYTHONPATH=src python -m unittest discover -s tests -v\`. GitHub runs the same suite on Windows and Linux.
