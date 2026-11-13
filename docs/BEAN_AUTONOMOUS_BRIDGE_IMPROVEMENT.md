# BEAN autonomous Bridge improvement: first real agentic milestone

**Acceptance target:** On a clean Bridge checkout, BEAN ranks competing
evidence-backed source issues, a narrow host-owned executor applies a
meaningful **code** change, baseline and post-change tests pass, a measurable
behavioral witness changes as predicted, and the isolated patch becomes a
reviewable pull request. A policy description by itself is NOT success.

## What makes this BEAN-driven

The Bridge checkout includes BEAN Core under _bean_core. BEAN's
bean.optimization.selection chooses among reproducible opportunities, and
SelfOptimizationGovernor records the chosen proposal and sandbox approval.
A distinct trusted executor implements only its reviewed transformation set.
This is genuine bounded agentic source modification, **not** open-ended
LLM-generated code or a claim of general self-programming.

### Current opportunity catalog

1. **Invalid direct Observation ingestion:** A direct dataclass constructor
   can bypass Observation.from_dict validation. The agent first proves the
   old Ledger accepts an invalid timestamp, then injects validation at
   the durable write boundary. New tests verify malformed timestamps,
   blank identity, bad payload atomicity, idempotent valid writes.
2. **Repeated latest-entity timestamp parsing:** The agent measures excess
   datetime parses when selecting the latest observation. It can replace
   the function with a cached-timestamp equivalent and add tests covering
   parse count, latest-wins and future-event filtering.

BEAN scores candidate impact, repeatability, observed confidence, risk
and availability of independent tests. Only one candidate is attempted per
run. Each subsequent run re-inspects current main and may choose a different
remaining candidate. Once the catalog is exhausted, BEAN reports no eligible
candidate and **does not generate a pointless change**. Adding new trusted
transformation capabilities requires normal code review.

## Host contract

- Real source edits in src/ezbean/core.py or src/ezbean/store.py, plus
  scoped new tests only. Any other write is forbidden.
- Source-level pattern checks and executable before-change witnesses are
  required before a candidate can be offered to BEAN.
- No arbitrary code/shell commands are accepted from the model, an issue,
  a document or an untrusted prompt. Test commands are fixed locally.
- Full unittest regression suite must pass on baseline AND patched checkout.
- Independent witness must demonstrate a measurable improvement.
- On any failure, restore original file bytes and preserve a failure receipt.
- Store proposal, hashes, witness values, tests and rollback outcome as JSON
  in a **CI artifact**, not a fabricated performance claim.
- GitHub Actions may automatically create a candidate branch/PR, but never
  merge to main. Production CI and human review remain the merge gate.

## Local reproduction

From Bridge root, with BEAN cloned alongside into _bean_core:

    PYTHONPATH="src:_bean_core" python tools/bean_bridge_agent.py --receipt .bean-agent/receipt.json
    PYTHONPATH="src:_bean_core" python tools/bean_bridge_agent.py --apply --receipt .bean-agent/receipt.json

Default is read-only planning. --apply mutates at most one selected source
file and adds its regression test in the **local** working tree. The
workflow runs on manual dispatch, daily schedule and the first push to
main that installs this workflow. It also tests the patch on a PR checkout
without pushing it.

## Honest limitations

The current agent can autonomously choose, make and test changes only among
known transformations. An LLM is optional and does not determine source
execution permissions. Reproducible synthetic witnesses do not prove general
software engineering intelligence. GitHub App/workflow settings may prevent
the token from creating a PR, in which case check the recorded branch and
workflow error rather than claiming the PR exists. GitHub Action PRs created
with GITHUB_TOKEN may not trigger all other workflows automatically, so
cross-platform acceptance must be verified separately.
