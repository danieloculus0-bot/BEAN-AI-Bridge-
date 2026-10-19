# BEAN engine firing and connection sweep — 2026-10-19

**Objective:** Confirm existing BEAN components are connected correctly, without
adding new cognitive modules or behavioral restrictions. This is an integration
diagnostic, not a new release or a claim of artificial general intelligence.

## Two independently checked branches

- **Core:** `fix/engine-firing-sweep-20261019` (based on the earlier audit-repair branch)
- **Bridge:** `test/engine-firing-sweep-20261019` (based on the pilot-readiness branch)

All probes use **fictional local data** and actual Core/Bridge Python functions
and SQLite stores. The real `bean_run.py` simulator process is executed
for two ticks by GitHub Actions on both operating systems. No physical
hardware or live LLM account is used.

## Engine wiring map

| Existing components | Tested connection | Verification | Scope |
| --- | --- | --- | --- |
| Actual `bean_run.py` -> main `BeanLoop` -> tick handlers | **Connected** | Start a real process with two ticks; inspect session-start/end, reflection, consolidation records; assert no `tick_handler_error` events | Actual scheduled Core runtime |
| Event logger -> SQLite / JSONL memory -> startup continuity | **Connected** | Structured observation and source IDs survive close/reinit and second boot | Persistent Core cognition |
| Reflection -> curiosity | **Connected and repaired** | Same error/evidence reflected twice; only one unresolved curiosity question generated | New Core regression |
| Curiosity -> goal proposals | **Connected and repaired** | Duplicate pending goals reused while a second question remains a distinct goal | New Core regression |
| Structured observations -> reasoning context | **Connected** | Stored event `data` available as structured JSON; offline mock reasoning proposal created | No claim of live Ollama reasoning |
| Core event memory -> Bridge memory block | **Connected and repaired** | `bean.memory_recall` returns decoded nested JSON event payload, not an opaque JSON string | Core block wrapper, same SQLite |
| Bridge Scratch ports -> analysis -> forecast | **Connected and repaired** | Index `events.0.data.samples` transfers a Core observation to a downstream Bridge Core block | Bridge graph runner |
| Bridge module chooser -> observed reward -> method preference | **Connected** | Two existing Core predictors scored on training inputs; preferred method changes on unseen holdouts after SQLite reopen | Deterministic synthetic tasks |
| Bridge experiment run IDs -> Core memory events | **Available by explicit wiring in integration test** | Every Bridge reward receipt linked to `EventType.PREFERENCE_UPDATE` in Core with the same run ID | **Not auto-dispatched from the ordinary Core tick loop** |
| Existing generic RMA replay GitHub workflow -> tests | **Repaired CI** | Install `pytest` needed by tests imported via `unittest discover` | Engineering build correctness |
| Windows non-Unicode console -> Core startup | **Repaired** | Core startup banner uses ASCII so cp1252 output cannot prevent first tick | Checked via actual subprocess |

These tests are intended as functional checkpoints. As with any CI run,
refer to the linked GitHub Actions result and corresponding commit when
claiming final pass status.

## Where the real circuit is still open

1. **Goal selection -> autonomous Bridge invocation:** In `bean_run.py`,
   scheduled consolidation creates goal proposals, but none inherently
   dispatches a chosen Bridge logic block. The Bridge runtime is available
   and independently tested, but does **not** run just because Core produces
   a pending goal. This is an actual integration gap.
2. **Bridge learning -> automatic Core updates:** Reward feedback is retained
   by Bridge. The integration test explicitly calls Core's event logger and
   preference engine using Bridge receipt IDs, demonstrating the usable
   interface, but no default background process transports these receipts.
3. **Autonomous reasoner:** `ReasoningEngine` is accessible through Core
   commands and tests. The ordinary default tick loop runs model updates,
   reflection, coherence and consolidation but does not independently
   schedule an Ollama inference and use its result as a strategy proposal.
4. **Unseen task generalization:** Existing method-choice tests measure
   learned preference on synthetic forecast fixtures. This is not proof that
   BEAN improved general reasoning on novel tasks.
5. **Actual Jetson and hardware:** A two-tick cloud simulator cannot prove
   robot electrical/physical behavior, actuator readiness, or Jetson-specific
   timing. The local Ollama model also wasn't exercised by GitHub CI.

## Architectural conclusion

**The individual parts largely work, and their existing interfaces can
exchange information.** Several real data-contract and repeated-state bugs
were found and corrected. The missing piece is a normal operation-level
closed-loop connection between **a chosen question/goal, the available
Bridge modules, an observed experiment outcome, and Core's retained
experience**. The integration harness demonstrates the wiring explicitly,
not spontaneous autonomous decision-making.

The next sensible engineering increment is to connect those **already
existing** subsystems using actual task/outcome signals—not invent more
cognitive layers, synthesize fake rewards, or install behavioral gatekeepers.

## CI evidence

- Core full regression: https://github.com/danieloculus0-bot/BEAN/actions/workflows/bean-engine-firing.yml
- Bridge cross-repo/full regression:
  https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/workflows/bean-engine-firing-sweep.yml
- Native BEAN RMA replay:
  https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/workflows/bean-rma-1618.yml

Core and Bridge remain on separate draft branches. No real personal/company
data, new cognitive modules, website modifications or merges to `main`.
