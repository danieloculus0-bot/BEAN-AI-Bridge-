# BEAN Connected Cognition — First Runnable Core/Bridge Loop

**2026-10-19 — experimental branch.** This is a functioning cross-repository
integration, not a claim that BEAN already understands arbitrary problems,
rewrites neural weights, or autonomously discovers the ground truth.

## Actual connected subsystems

1. **Core observations:** `bean.observe_experiment` records an observation
   event with the supplied expected outcome and creates a native curiosity
   question in Core SQLite. Both are linked to the actual session.
2. **Core goal formation:** `GoalStateEngine.propose` recognizes a structured
   experiment question and creates a native `run_experiment` goal, without
   duplicating outstanding work. Other plain-language questions retain their
   existing behavior.
3. **Bridge module selection:** `CognitiveDispatcher.poll` finds pending
   Core experiment goals, asks `BlockRuntime` to choose an available matching
   module, and runs it. During exploration, untried modules get tested before
   previously measured choices are exploited.
4. **Measured feedback:** Bridge compares outputs to an *already observed*
   result, updates the per-capability module preference and retains the
   exact code revision/run receipt in Bridge SQLite. Missing expected values
   aren't made up by the program.
5. **Return to Core:** Bridge records the module's result and score in native
   Core events. `FACT_LEARNED` events link to the actual curiosity question
   ID; the existing ConsolidationEngine resolves **that** question only.
   A failure remains recorded as a negative experiment, without inventing an
   answer.
6. **Future reasoning:** Core's existing `reasoning`, `drive_evaluation`,
   and `memory_recall` modules are exposed in Bridge's same catalog. A
   model can read structured experiment outcomes from Core context; the
   first experiment loop does not require a model or cloud inference.
7. **Runtime:** `build_default_handlers(cognitive_dispatcher=dispatcher,
   cognition_interval=10)` registers the experiment consumer in Core's
   existing tick-based scheduler. This is optional integration, not a
   replacement runtime.

No scripts hide the process behind fake output. The demonstration uses native
Core SQLite and goal/curiosity/event tables, Bridge's real module catalog,
plugin loader and persisted feedback selection. The fixture is deliberately
simple so improvement can be directly measured and rechecked.

## Windows run — separate test checkouts, avoiding your existing BEAN workspace

```powershell
git clone -b feature/connected-cognition-20261019 https://github.com/danieloculus0-bot/BEAN.git D:\BEAN\experiment-core
git clone -b feature/connected-cognition-20261019 https://github.com/danieloculus0-bot/BEAN-AI-Bridge-.git D:\BEAN\experiment-bridge
cd D:\BEAN\experiment-bridge
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m examples.connected_cognition --core "D:\BEAN\experiment-core" --data-dir "D:\BEAN\data\cognitive-test"
```

The databases are `cognitive-test/core.sqlite` and
`cognitive-test/bridge.sqlite`, separate from the user's regular
`bean_memory.db`. Omit `--data-dir` to run a temporary disposable test.
The default Bridge catalog can also download the registered Core branch
on first use if no local Core checkout is provided.

## CI

- Core full regression: https://github.com/danieloculus0-bot/BEAN/actions/runs/39259043472
- Bridge cross-repo & actual demo: https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/39259555957
- Bridge runs on Windows/Linux with Python 3.10 and 3.12; the old Bridge
  unittest suite also runs on both. All six jobs passed at this revision.
- Core runs the complete regression on Windows/Linux, Python 3.10 and 3.12.
  All four passed at this revision.

## Scope and known limits

- This first scheduler handles **structured observable questions**. Unstructured
  reflections are not yet automatically translated into experiment
  specifications or scored without independent evidence.
- The forecast task uses simple synthetic numeric arrays and already known
  outcomes. These results establish module interoperability and reward-based
  method selection, not transferred intelligence or predictive market success.
- Exploration currently tests methods without learned visits first. Selection
  is reward-mean based rather than a richer context-sensitive planner.
- Core identity/memory and Bridge's separate local policy database persist
  across restarts, but there is no fully coordinated transaction spanning the
  two databases. An interruption between Bridge feedback and Core event
  logging may require idempotent reconciliation later.
- The Core reasoning engine can be selected as a block. It is **not yet
  autonomously choosing tools from model-produced plans or independently
  grading natural-language hypotheses.**
- Tests use isolated virtual environments and do not actuate hardware, spend
  funds or publish private observations.

**Next step:** request/answer matching for naturally generated curiosity,
contextually ranked memory retrieval, more sophisticated task-specific reward
functions, and replay across Core and Bridge interrupted transactions.

No new executable behavioral restrictions; safeguard ideas remain comments
for later architectural discussion.
