# BEAN Lab 008: dynamic knowledge library and primary output acceptance gate

**Status:** Experimental and isolated from production. **Core artifact:** [src/ezbean/knowledge_gate.py](../src/ezbean/knowledge_gate.py). **Tests:** [tests/test_knowledge_gate_lab008.py](../tests/test_knowledge_gate_lab008.py). **Repeated model evaluation:** [experiments/knowledge_lab/run_lab008.py](../experiments/knowledge_lab/run_lab008.py).

## Objective

Before a language-model answer is considered usable, verify that it follows the current, dated, evidence-identified definition snapshot. Do not rely on text-generation confidence. The *library is authoritative for its own source-reviewed entries*, not automatically for the outside world. The model cannot publish definitions by making predictions.

The output path:

1. **Human-reviewed or separately verified source** writes an immutable definition revision to SQLite with explicit evidence IDs, status, UTC validity start and optional expiry. (Lab 008 uses **fictional synthetic fixtures** only.)
2. Bridge's DefinitionLibrary performs a timestamped, latest-revision as-of lookup. Provisional, expired, retracted, never-seen and future definitions are treated as unavailable. Historical queries can still access earlier versions at their original time.
3. A provider (local Ollama adapter or test fake) receives the selected snapshot. A model proposes `{concept, decision, value, definition_ids}`.
4. **OutputGate.verify** uses deterministic code, not another LLM, to check exact query identity, current definition revision ID, canonical value, shape and abstention.
5. Only an accepted current library value is emitted as the answer. Invalid proposals produce **no output**, not an embellished answer or guessed reference.
6. Each run preserves machine-readable outcomes and reason codes for inspection. The fixture runner never writes BEAN trust scores, BEAN Core memory, or the model's weights.

**Interpretation:** This is *syntactic and referential grounding*, not full semantic truth verification or a proof the Ollama model knows a fact. The origin of a definition remains subject to external authentication and confidence handling. No assertion in this experiment means the models have consciousness or subjective feeling.

## Invariants under repeated testing

- 25 identical model lookups of `affection` return the same approved versioned text.
- Updating `affection` does not alter or increment independent `trust` definitions. Social warmth never becomes reliability evidence by implication.
- Stress is modeled as one possible explanation for harsh behavior, never as proof of harmless intent; safety rules stand separately.
- Later verified definitions supersede earlier ones **from their valid time forward**, without corrupting historical as-of answers.
- Expired, retracted, provisional and missing concepts must abstain; there is no fallback to outdated revisions.
- Hallucinated reference IDs, stale IDs, extra keys, incorrect value text, wrong concepts and invalid JSON must be rejected.
- "Verified" means *upstream reviewer asserted source status and supplied an evidence reference*; the gate itself does not authenticate the source.

## Run deterministic smoke tests

Python 3.11+, stdlib only, at repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_knowledge_gate_lab008.py -v
PYTHONPATH=src python -m unittest discover -s tests -v
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p 'test_knowledge_gate_lab008.py' -v
python -m unittest discover -s tests -v
```

## Live local Ollama protocol

Requires an actually installed local `ollama` daemon; the CI comparison uses `ollama pull qwen2.5:1.5b`. No remote/cloud provider fallback.

```bash
PYTHONPATH=src python -m experiments.knowledge_lab.run_lab008 --model qwen2.5:1.5b --repeat 3 --out lab008-live-output-gate.json
```

Thirty calls are made in alternating forward/reverse orders across ten synthetic concepts, including a revised calibration code whose answer depends on requested date. Each call records *candidate acceptance*, not independent fact correctness. The full report counts failures by reason, so repeated underperformance is visible even if some calls pass.

GitHub Actions workflow: [.github/workflows/bean-dynamic-definitions-lab008.yml](../.github/workflows/bean-dynamic-definitions-lab008.yml). Both Linux and Windows rerun all deterministic checks; Linux additionally spins up a **real local Ollama model**, runs the repeated protocol, and uploads a JSON artifact.

## Next integration step

Wire this gate into actual BEAN reasoning/provider output dispatch only after multi-model evaluation and independently authenticated definition ingestion. Keep ERP deterministic KPI calculations and the BEAN Core relationship/trust model separate. All concepts in this lab are intentionally example-only, not an authoritative ontology.

**Primary mechanism** here means mandatory contract validation for **this experimental output path**. It does not yet govern every existing BEAN or ERP response.


## First measured Ollama baseline (run 38033085153)

The Qwen2.5 **0.5b** 30-query repeat experiment produced **9 accepted abstentions, 21 rejected/failed, and no accepted canonical answers**. It showed 15 stale/hallucinated-reference rejections, 3 model/server HTTP 500 errors, 3 incorrect answers where definitions were missing, and 9 accepted abstentions. This is a **failed model-output fidelity baseline**, not a successful verification. The gate did its job by blocking all rejected values from the approved final-output channel.

[Machine evidence and original experiment log](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38033085153) and [JSON artifact](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38033085153/artifacts/11662637326).

A second experiment uses a stronger 1.5b local model and captures raw, untrusted candidates and server diagnostics so failure causes can be inspected. Avoid assuming bigger models guarantee adherence; compare measured acceptance rates.


## Second measured Ollama comparison (run 38033296146)

Qwen2.5 **1.5b**, same 30-query test: **29/30 accepted (96.67%)**, including **17/18 canonical definition lookups** and **12/12 abstentions**. One malformed first-run citation returned numeric `1` instead of the current library ID `affection@1`; the gate rejected it. Raw untrusted replies and the Ollama server log are archived for auditing. This is promising fidelity on a limited synthetic lookup task, not proof of factual truth or real-world model reliability.

[Successful real-model run](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38033296146) and [raw JSON/diagnostics artifact](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38033296146/artifacts/11662223228).

**Promotion gate:** Future live CI requires at least **27 of 30 total accepted** and at least **16 of 18 accepted verified lookups**; otherwise the workflow must fail. This prevents a model that simply abstains on everything from passing.
