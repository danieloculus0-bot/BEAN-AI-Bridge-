# BEAN Native 0.1 - LAB009 architecture exploration

**Research status:** Prototype inference-gateway architecture optimizer, not an independent neural foundation model or a drop-in Ollama replacement.

BEAN now has a runnable standalone **symbolic inference service** exposing a restricted, Ollama-like HTTP interface (\`/api/chat\`, \`/api/tags\`, \`/api/version\`) on loopback. Its output contract is very deliberately narrow: a caller must supply an exact concept and an as-of UTC timestamp inside the final message JSON. BEAN Native produces verifiable answers from the versioned definition ledger, or an explicit abstention. It does not invent missing knowledge.

## Current architecture

```text
 BEAN schema + provenance library
           |
           v
 BEAN Native optimizer (genome generator + fitness / heldout testing)
           |
           +-- blueprint: Ollama JSON, schema, retry, fallback, native fast path
           |
           v
 Generic gateway router
    |                |
    +-- symbolic      +-- Ollama reference backend (real model locally)
         answer                 |
    |                           v
    +----------- output verification against current ledger
                         |
                  safe result / abstention
                         |
                  BEAN Core governance proposal (no execution)
```

**The source of truth is the stored, versioned definition.** No model can win simply by returning a confident but ungrounded answer.

### What BEAN can change in this lab

Each `Blueprint` is a four-gene architecture: \`canonical_fast_path\`, \`json_schema\`, \`retry_invalid\`, and \`safe_fallback\`. A reproducible, seed-controlled optimization agent mutates configurations, measures training fitness, and selects the highest-scoring contender. The candidate must then face an entirely separate, disjoint-concept held-out corpus. Each rejected model output and failed design remains in the raw evidence ledger.

The algorithm can **choose and recombine gateway strategies**, but cannot arbitrarily edit executable source, retrain weights, or change the validation rules. These limits ensure a meaningful baseline; expanding the mutation grammar to lower-level inference algorithms should happen only after verifying results here.

### Real and synthetic comparisons

The exact same 10 held-out concept/time queries are posed to the baseline unmodified local Ollama output generator and to BEAN's selected gateway. We track accepted canonical answers, correctly accepted abstentions, rejected candidates, number of model calls, and elapsed wall-clock time. Selection never uses the held-out corpus.

**Fairness caveat:** Native symbolic retrieval can be more reliable and faster than asking a language model to *copy* a definition, but it is **not** a competing general-purpose text generator. No claimed improvement in model reasoning, intelligence, language understanding, or arbitrary token throughput follows from this experiment.

### How to run

From the bridge repository root using Python 3.11 or newer:

```bash
PYTHONPATH=src:. python -m unittest discover -s tests -p test_native_lab009.py -v

# Real Ollama daemon must be running with the referenced model installed:
PYTHONPATH=src:. python -m experiments.native_engine.native_lab \
  --model qwen2.5:0.5b --seed 106 --iterations 10 \
  --output-dir lab009-results --bean-core ../BEAN
```

The GitHub Actions workflow tests the full bridge and independent BEAN Native HTTP service on Linux and Windows. A separate Linux job starts an actual local Ollama model, calls its supported version/tags endpoints, benchmarks the reference on the same as-of queries, runs BEAN's architecture mutations, and writes:

- `lab009-results.json` with the full training leaderboard, every proposed genome, and withheld baseline/winner cases
- `winner-blueprint.json`, `reference-comparison.json`
- `governor.sqlite` and `bean_governor_proposal.json` from **real BEAN Core** SelfOptimizationGovernor
- `ollama-server.log`, when available

### Run the independent local HTTP server

Provide a SQLite database containing definitions that were explicitly curated or verified:

```bash
PYTHONPATH=src:. python -m experiments.native_engine.http_gateway \
  --database /path/to/curated-definitions.sqlite --port 11435
```

Call \`POST http://127.0.0.1:11435/api/chat\` with JSON containing \`model: "bean-native:symbolic"\` and an array of messages whose last \`content\` is a JSON string with \`concept\` and \`as_of_utc\`. \`GET /api/tags\` and \`GET /api/version\` expose the provider's constrained capability. It does not claim Ollama model or GGUF compatibility and cannot answer free-form questions yet.

### Source maps and next research

Ollama API descriptions support \`/api/chat\`, model lists, structured JSON outputs and generation timing: [official API](https://docs.ollama.com/api) and [official structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

Probe reports describe only **publicly observable API capabilities**. We have *not* reverse engineered attention kernels, tokenizers, quantized model execution or GPU scheduling. The next fair head-to-head test needs a real independent model backend (such as a separately integrated llama.cpp runtime) using identical weights, sampling settings and hardware, alongside open-ended task evaluation and measured throughput. Until then, BEAN Native is an evolving gateway that performs grounded symbolic retrieval and governs replaceable neural backends.

**Nothing here updates the production BEAN database, Ollama code, or BEAN Core main branch.** BEAN Core receives a **proposal record only**.
