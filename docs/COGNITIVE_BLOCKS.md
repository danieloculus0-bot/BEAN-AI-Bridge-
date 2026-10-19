# BEAN Bridge: logic-module communication

**Status:** experimental software capability, not general self-improvement or automatic learning across every BEAN layer.

BEAN AI Bridge owns a common block interface. A block is an independently
developed Python function: `callable(payload: dict, context: dict) -> dict`.
Core and other apps **expose** modules; the Bridge catalogs, discovers, loads,
chooses, wires and records module outcomes. A list of steps works like Scratch
blocks. Output-port references `{"$from": "step.field"}` connect modules.

## What works
- Lazy module loading: reading the catalog does not import or download code.
- Registered branches: a module's `source.git_url`, `ref`, `python_root`
  and `module_file` let Bridge clone and compile Python when selected.
- Offline/local-root sources: keep the downloaded checkout and rerun without
  internet; or register an existing local Core checkout from the start.
- Module selection: choose based on average reward recorded after observed
  task outcomes. A caller can force a module for exploration/training.
- State: Bridge retains selection history in its own SQLite database; the
  Bridge's existing Lab010 policy separately retains `bridge-online-policy.json`.
- Different databases: Core owns its identity and event memory; Bridge
  owns module communication and preference/outcome tracking.

## How to run
Use Python 3.10+ from the Bridge repository with `PYTHONPATH=src`:

```bash
python -m examples.cognitive_blocks --core /path/to/local/BEAN
```

To test Git branch retrieval, omit `--core`, which pulls the registered
Core branch **only when its first block is selected**. Git is required for
that mode. This is an on-demand repository checkout and Python bytecode
compilation, not arbitrary automatic C/C++ compilation.

Run `python -m pytest tests/test_cognitive_blocks.py -q` for Bridge-only
replay and `BEAN_CORE_PATH=... python -m pytest tests/test_cognitive_blocks.py -q`
for both repos.

## Bridge graph example

```json
[
  {
    "id": "analysis",
    "capability": "numeric_context",
    "payload": {"history": {"$from": "input.history"}}
  },
  {
    "id": "prediction",
    "capability": "binary_forecast",
    "payload": {"history": {"$from": "analysis.history"}}
  }
]
```

Call `runtime.feedback(run_id, observed_reward)` to change the selection
policy for the next invocation of the same capability. Without measured
feedback this is just composition, **not learning**. Native Core experiments
compare last-sign vs mean-sign prediction on holdout inputs and restart the
Bridge process/database. Bridge's own Lab010 learner remains separate,
accessible as the `bridge.strategy_policy` block with `choose` and
`feedback` modes.

## Later (comments only)
Potential GUI drag-drop programming, richer block ports/type metadata,
independent repository revision policies and permission review are future
research. This implementation does not update the website or merge to main.
