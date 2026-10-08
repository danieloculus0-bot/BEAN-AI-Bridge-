# Design memory: EZ-BEAN and generic implementation layer

Recorded 2026-10-08. Architecture decision and public-safe executable proof.

## Non-negotiable separation

- **EZ-BEAN is the ERP-facing operational thinking module**, behind EZ Fabricating KPI reporting. It is not a reporting slide deck, UI, or war-room skin.
- **BEAN may be integrated as its evidence-aware reasoning and reflection layer.** It must not manufacture numerical KPIs or claim causation from correlation.
- **Generic implementation layer is reusable outside EZ Fab.** Organization-specific job codes, people, machines, customers, costs, credentials, and other proprietary records do not belong in this public repository.
- **64Δ is explicitly excluded.** No dependency or integration with that separate project.

## Runtime expectations

1. ERP adapter observes authorized read-only source changes and reports source IDs, timestamps, and explicit field mappings.
2. Event ledger persists normalized observations, rejects conflicting reused source-event IDs, and supports retrospective replay.
3. Deterministic calculators derive KPIs only from evidence and documented formulas. Missing denominators and invalid data are surfaced rather than silently converted to 0.
4. Thinking module generates evidence-backed attention signals, investigates alternatives, flags uncertainty, and records hypotheses separately from verified findings.
5. Versioned report contract feeds a future command-room display without tying display behavior to ERP access.
6. Scheduled or triggered smoke tests use synthetic scenarios on actual headless Windows and Linux CI hosts. Local offline replay requires no secrets or live ERP connectivity.
7. AI-generated test scenarios must be checked against independent deterministic expectations. The AI does not grade itself.

## First executable generic test path

`FixtureAdapter -> Ledger -> calculate -> RuleThinkingModule -> JSON report`

Run on Windows and Linux through `.github/workflows/ez-bean-smoke.yml`; locally run `unittest` and the demo CLI. The synthetic tests check duplicate inputs, conflicting event identities, historical corrections, as-of replay, missing denominators, invalid data, evidence tracing and determinism.

## Domain logic target

ERP facts should eventually support agreed KPI definitions for on-time delivery, open past-due commitments, RMAs/returns, actual production, scrap/rework, and additional metrics only where the source provides evidence. Compare targets and trends only after configured targets and historical baselines are explicitly supplied.

## Future ERP integration contract

Read-only authenticated ERP access; incremental checkpoints; mapping of order, promise, shipment, return, production, maintenance and equipment states; source-data lineage; source priority; policy-approved OTD granularity; freshness thresholds; reconciliation against authoritative ERP reports; access controls; recording of investigated anomalies and decisions.

**No claim of live ERP access or production deployment is made in this milestone.**
