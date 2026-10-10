# BEAN Lab 006 — Learning never closes

October 10, 2026. Status: **isolated experimental branch**.

## Foundational design rule

**A decision may be settled for now; a claim may never be designated unlearnable.**
A score of 100% certainty is inappropriate for claims about physical or empirical
phenomena, even when a controller processes apparently binary values. Digital
representations are implemented by physical measurements with finite noise,
thresholds, drift, and unknown conditions.

This does *not* mean all micro-variations matter equally. BEAN must retain
observations and assess decision relevance with explicit cross-abstraction paths:

    Physical signal
        |
        | measured by a recorded instrument, with uncertainty
        v
    Measurement / calibration
        |
        | explicit causal or specification link with rationale
        v
    Claim / competing explanations
        |
        | topical and decision relevance, independently audited
        v
    Decision or search-ranking priority

The graph never fabricates an implication from mere proximity. An irrelevant
fluctuation remains in the evidence ledger, with zero *current* decision
priority; later established connections can make it relevant.

## Implemented in experimental code

- `epistemic_continuity.py`: continuous empirical belief model; finite
  confidence bounded away from exactly 0 and 1; observation provenance;
  explicit relevance links; contradiction-triggered reopening; preserved
  physical deviations; per-origin de-duplication and distinct verified sampling
  identifiers.
- `confidence_search.py`: multiple search episodes share the same
  research evidence graph. Ending one search after satisfying a fetch budget
  does **not** switch off learning or prevent a later search from challenging it.
- Search results may optionally carry a measured physical deviation,
  measurement uncertainty, cross-layer relevance coefficient and a
  documented basis. These fields are **not inferred from ordinary webpages**.
  If absent, no physical measurement or causal connection is invented.
- The search score separates topical relevance from claim support. An
  unverified page is recorded as such. Evaluator feedback is recorded as
  a separate verification observation. Repeated copies may be stored without
  being counted as independent confirmation.
- Reports only expand ancestors relevant to the current decision; historical
  evidence stays preserved in the in-memory ledger rather than repeatedly
  traversed for every query.

## Key invariants tested

1. At extremely strong prior evidence, the empirical confidence score still
   has a nonzero residual-uncertainty floor.
2. A contradiction from an independently verified source can reopen an
   apparently settled belief, even when the prior confidence was extremely high.
3. Repeat syndicated reports do not vote several times; independent
   subsequent measurement samples can be recorded and reconsidered.
4. A micro-scale fluctuation is retained without an automatic ranking effect.
   Providing an independently justified physical-to-claim relevance connection
   allows the signal to propagate to the decision layer.
5. Search routing, decision and source confidence tracking continue across
   individual query boundaries.
6. A rejected or ungrounded physical relevance claim is not accepted.

## Important limits and design implications

- This is an experimental **in-memory** graph; it does not yet implement
  production durability, reindexing, retention policy or web crawling.
  Perpetual learning requires a persistent append-only store plus compaction
  into auditable derived summaries, not infinite RAM.
- The numeric confidence is a research heuristic, not an empirically
  calibrated probability or a guarantee of correctness. Its epsilon
  uncertainty floor is a design safeguard, not a measured physical noise floor.
- There is a distinction between logical certainty *given axioms* and
  empirical certainty about the physical world. This model governs empirical
  claims.
- This study uses synthetic search hits. The base ranking experiment must be
  independently tested with real webpages, verified reference datasets and
  blind evaluation before any claim about search-engine superiority.
- Decisions can conclude within a budget; continued learning should be
  resource-governed so a high-confidence answer does not trigger endless
  unnecessary probes or battery/network use.
- No AIscend changes and no changes to either repository's main branch.

## Next gates

1. Persist these provenance and abstract-layer edges to the existing BEAN
   memory and replay model, with versioned linkage and migration tests.
2. Incorporate proper uncertainty intervals, selective verification bias,
   repeated correlated evidence and reliability change points.
3. Build a read-only browser adapter that collects *actual* citations,
   publication dates, ownership/originality and independently checkable
   claims without claiming physical measurements that webpages do not supply.
4. Let BEAN select follow-up searches by expected information gain and
   value of resolving a particular uncertainty, not just fixed stream bonuses.
