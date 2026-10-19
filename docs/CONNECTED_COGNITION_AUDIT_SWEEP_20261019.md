# BEAN Connected-Cognition Audit Sweep
**Date:** 2026-10-19  
**Repos:** [BEAN Core](https://github.com/danieloculus0-bot/BEAN), [BEAN AI Bridge](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-)  
**Exact audit branches:** Core `feature/connected-cognition-20261019` (head `3e77f84c73289cdd6c763380cc6e768b2f0a4b80` at sweep start); Bridge `feature/connected-cognition-20261019` (head `4acfc8cd81e0716b2a7694af80206b8eea061a1f` at sweep start).  
**Remediation branch:** Bridge `fix/cognition-audit-sweep-20261019`, stacked on Bridge PR #39.

## Executive judgment

**CONTINUE, with constrained engineering scope — not a new cognitive-layer expansion yet.**

BEAN now has a **real, local, testable communication path** across Core
observation → curiosity → goal → Bridge module selection → execution →
scored outcome → Core native event/memory → subsequent selection.
This is substantially more than a static demonstration of disconnected
classes. It is **not** yet a self-originating cognitive system that plans
tests for arbitrary questions or demonstrates domain-general learning.

The best next investments are making the existing loop **truthful,
restart-reconcilable, and context-sensitive**, and then adding an actual
planner that turns naturally generated Core questions into experiments.
No new executable behavioral safeguards were requested or implemented.

## Verified functionality

| Component | Evidence | Status |
| --- | --- | --- |
| Core question + goal state | `bean/modules/builtin.py`, `bean/cognition/goal_state.py` | Runnable for structured, externally supplied experiments |
| Bridge module discovery and load | `src/ezbean/modules/catalog.py`, `modules/runtime.py` | Git/local-root Python modules load on first use |
| Core/Bridge dispatch | `src/ezbean/cognitive_dispatch.py` | Uses native Core SQLite questions/goals/events, Bridge SQLite feedback |
| Adaptive module choice | `BlockRuntime.feedback`, `choose` | Method selection changes after measured rewards and survives restart |
| Scheduler interface | `bean/runtime/tick_handlers.py` | Optional `cognitive_dispatcher` plug-in, **not registered at default boot** |
| Runtime demonstration | `examples/connected_cognition.py` | Real code and two local SQLite databases; prepared numeric inputs |
| Cross-platform checks | Bridge `bean-cognitive-blocks.yml`, Core `bean-audit-reliability.yml` | Prior paired CI passed 6 Bridge and 4 Core jobs |
| Held-out comparison | `test_cognitive_dispatch.py` | 0/4 cold vs 4/4 selected on four **constructed synthetic examples**, NOT evidence of broad generalization |

## Audit defects found and repaired in this sweep

1. **HIGH — Wrong answer became resolved knowledge.** Previously a
   mismatch still emitted `FACT_LEARNED` and closed the curiosity row.
   Now only an observed match to the supplied expected result closes this
   particular test question. A mismatch remains as a negative observation.
2. **HIGH — Failed hypotheses didn't cause systematic per-question
   alternatives.** The dispatcher now tracks the methods already attempted
   for that question (including thrown exceptions), explores alternatives,
   leaves a question open when all current modules fail, and can resume it
   when another module is registered. This is experiment feedback, not a
   new behavior restriction.
3. **MEDIUM — Missing output key could falsely match expected `None`.**
   Matching now requires each expected key to actually exist in the output.
4. **MEDIUM — Repeated scanning of all event history per question.**
   The dispatcher now builds one attempt index per tick, preventing
   repeated full-history scans for every unresolved question.
   Future work should use a durable incremental index.
5. **BUILD/CI — Existing ERP/RMA workflow runs `unittest` discovery
   without installing the `pytest` imported by current tests.**
   Added dependency installation to that workflow. The app logic did
   not need alteration for this runner issue.

Tests in `tests/test_cognitive_dispatch.py` cover mismatch retry, no
false answer, exhaustion with an open question, later recovery when a
new method appears, and missing-key comparisons. The regular cross-repo
and full Bridge suites are rerun on this branch.

## Important unresolved weaknesses

### P1 — Cross-database crash reconciliation
The Bridge reward/receipt and Core event/curiosity updates are **two
independent SQLite commits**. A process can crash after recording
Bridge feedback but before marking the native Core question, leaving
a partially applied experiment. Neither an idempotent shared
experiment ID nor transactional outbox reconciliation is implemented
for this cross-repository boundary. Do this before long-lived,
unattended experimentation.

### P1 — No automatic unstructured curiosity → experiment planning
Most Core-generated questions are still ordinary text.
The current runnable experiment requires a schema, named capability,
inputs and an expected observation. It does not independently produce
hypotheses, test design, method choice and grading criteria from an
open-ended question.

### P1 — Context-insensitive learned preferences
`BlockRuntime` keeps a **single reward mean per capability and block**.
It does not learn which method wins in which context, may over-generalize
from tiny samples, and cannot express competing context-dependent
hypotheses. Explore richer dynamic learned state before expanding
tool categories.

### P2 — No atomic concurrent trial claim
`CognitiveDispatcher.poll` reads pending goals and then runs modules
without an atomic claim of an individual goal. Two simultaneous pollers
can run a single goal twice. Native Core goal updates do not currently
provide a durable multi-runner experiment lease or recovered in-progress
attempt state.

### P2 — Weak long-range relevance
Core context only includes the most recent 20 same-session events;
the small Ollama prompt selects three newest plus at most three recent
experiment events **within that limited packet**. Older, semantically
relevant cross-session experience is not recalled into reasoning by
this integration. SQLite persistence is not sufficient by itself.

### P2 — Limited runtime and reasoning proof
The Bridge dispatcher is an **optional** Core scheduler input, not
wired automatically during `start_bean` / normal `BeanLoop` boot.
GitHub tests invoke mock reasoning and simulated/local Python modules,
not the user's full local Ollama reasoning trajectory or a continuous,
self-directed task stream.

### P2 — Provisional evidence and confidence
Bridge's Lab009 definition-verification flow still requires multiple
verified source origins for **canonical** definition updates. The
experimental block loop operates alongside it and does not yet
maintain a unified probabilistic/provisional hypothesis record. The
user's desired flexible evidence/trust model is not implemented.

### P3 — Branch/version hygiene
Several Core and Bridge PRs are intentionally stacked, draft, and
unmerged. Local deployments must check out **matching experimental
branches**. CI success for an experiment branch does not mean those
changes are available in each repo's `main`.

## Recommended next milestones

1. **Cross-DB experiment ledger with idempotent recovery**, sharing
   `question_id`, `run_id`, module revision, and outcome between Core
   and Bridge. Simulate a crash after each possible commit boundary and
   verify exactly-once reward application.
2. **Naturally generated question planner**: map native Core curiosity,
   contextual evidence and current available tools into an explicit,
   testable experiment proposal; use provisional hypotheses rather than
   pretending to know the truth in advance.
3. **Context-dependent strategy learning**: compare across **unseen,
   changing regimes**, matched evaluation budgets and a do-not-learn
   control. Prove retained adaptation after process restart.
4. **Relevant cross-session memory retrieval**: provide source-backed
   observed examples to the local Ollama reasoning component.
5. **One clean integrated bootstrap**: register the cognitive dispatcher
   from the normal local runtime only after its interrupted/replayed
   experiments are observable and repairable.

## Decision boundaries

- **GO:** additional wiring, experiments, observations, and method-learning
  tests on disposable or intentionally chosen local databases.
- **NOT YET SHOWN:** autonomous open-ended problem-solving, durable
  end-to-end goal planning, retained improvement across diverse tasks,
  or real Ollama-guided experimentation.
- **Do not claim:** a self-improving brain, general intelligence, or
  safety certification because a few synthetic prediction tests passed.
- **No change:** website, private experiment archive, or executable
  behavioral safeguard policy.

This is a source-code and GitHub CI audit **performed in this chat**,
not an independent third-party model audit, and the findings are
bounded to the cited branches and observed tests.
