# BEAN LAB 009 — The Evidence Learning Loop

**Research branch:** [experiment/bean-learning-loop-lab009-20261010](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/tree/experiment/bean-learning-loop-lab009-20261010)  
**High-level module:** [`src/ezbean/learning_loop.py`](../../src/ezbean/learning_loop.py) (also exported as `from ezbean import EvidenceLearningLoop`)  
**Evidence harness:** [`run_lab009.py`](run_lab009.py)  
**Status:** Research; synthetic source verification and real BEAN Core SQLite integration. **Not a self-training LLM.**

## The previously missing loop

```
  Local model or other host proposes a response
                     |
                     v
       DefinitionLibrary + OutputGate
          |                   |
          | pass              | fail / stale / unavailable
          v                   v
  Safe bounded output   BEAN Uncertainty Garden
          |                   |
          |                   v
          |           Separate Investigator
          |                   |
          |                   v
          |       Independent host verification
          |                   |
          |       +-----------+-----------+
          |       |                       |
          | fewer than two,          two distinct
          | conflict, invalid        origins agree
          |       |                       |
          |       v                       v
          |  Remain unresolved       New immutable
          |  + preserve evidence     library revision
          |                               |
          +-------------+-----------------+
                        |
                        v
        BEAN Core events, epistemic audit,
        native context, permanent SQLite cycles
                        |
                        v
           New/repeated search or question
                        |
                        v
      Compare against withheld fixture answers
       separately for LLM and verified system
```

**No LLM output is a trusted evidence source.** The host owns the investigator and verifier implementations. A new definition is allowed only when at least two **distinct provenance origins** return the same value and each source record has passed a **separate host verification callback**. Contrary verified sources block promotion. Repeated copies from one origin cannot vote more than once.

The loop supports `refresh=True`: even an accepted model response or highly confident historical conclusion can be investigated again. Each episode has a finite source budget; **a decision can finish without learning ever becoming permanently disabled**.

## Measured replay

The included test harness uses an intentionally incorrect, **unchanged** model and a synthetic fixture-based independent verifier. The evaluator keeps its expected answers separate from the model.

1. Start with a missing sensor tolerance, obsolete calibration code, and a contradictory safety claim.
2. Record invalid model output, BEAN uncertainty, synthetic source observations and verifier decisions.
3. Append new definitions only for corroborated evidence; keep the contradictory safety claim unresolved.
4. **Close and reopen both SQLite databases** and run different, later-time requests including a new concept not in the first research batch.
5. Calculate the before/after system metrics and a separate model-success metric. Check native BEAN context and epistemic audits.
6. Preserve every cycle, evidence observation, original and revised definition, BEAN Core event, and uncertainty record. No hardware/financial actions occur.

Expected deterministic fixture result: **0/3 correctly answerable before → 3/3 after; 0/3 model answers accepted**. This is a software-system improvement in a controlled fixture environment, **not** evidence that Qwen or any other model updated its weights or developed intelligence. A real live-model benchmark and authenticated web-source verifier are different, uncompleted experiments.

## Run (Linux)

Requires Python 3.11+, `pytest`, `psutil`, a local checkout of [BEAN Core](https://github.com/danieloculus0-bot/BEAN), and no network runtime.

```bash
git clone https://github.com/danieloculus0-bot/BEAN.git bean-core
git clone -b experiment/bean-learning-loop-lab009-20261010 \
  https://github.com/danieloculus0-bot/BEAN-AI-Bridge-.git bridge
cd bridge
python -m pip install pytest psutil
PYTHONPATH="$PWD/src:$PWD/../bean-core:$PWD" python -m pytest tests -q
PYTHONPATH="$PWD/src:$PWD/../bean-core:$PWD" \
  python -m experiments.learning_loop.run_lab009 \
  --out lab009-evidence.json --evidence-dir lab009-audit
```

GitHub Actions repeats the test on Windows and Linux using pinned BEAN Core.
**[Open CI runs for experiment branch](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/workflows/bean-native-learning-loop-lab009.yml)**. Each successful run archives:

- `lab009-evidence.json`: before/after and held-out outcomes, provenance, reasons, context trace IDs.
- `lab009-audit/evidence_library.sqlite`: actual versioned library and complete cycle/receipt ledger.
- `lab009-audit/native_bean_core.sqlite`: BEAN's real cognition DB: sessions, events, uncertainties, epistemic audits and context packets.
- `lab009-tests.xml`: full regression evidence.

These archives are downloadable from **Artifacts** on each GitHub Actions run while GitHub retains them.

## Explicit limits

- The sample verifier relies on **researcher-defined synthetic fixture truth**, not independently authenticated external web or instrument measurements. Real source trust and provenance need a proper source adapter, content hashing, physical or documentary validation, and conflict-of-interest controls.
- A successful independent-source check still depends on verifier integrity and genuinely separate origins; the code cannot infer independence from two arbitrary domain strings.
- Without verified evidence BEAN retains an open question and withholds unsupported or contested answers, rather than hallucinating a repair.
- The system does **not** automatically schedule 24-hour work, pull live webpages, retrain local LLM weights or grant real-world execution permissions. It provides a callable learning cycle and persistent audit; a future authorized host supplies triggers, retrieval and verification.
- A held-out temporal case with synthetic fixture truth is narrower than distribution-shift generalization.
- BEAN Core's SQLite memory is a **process-level singleton**; use the journal in a dedicated worker or process, not in parallel multitenant web requests.

## Next independent gates

1. Integrate the Lab 005–006 confidence/provenance graphs and confidence calibration **without** treating numerical certainty as verification.
2. Apply to a read-only real browser/research adapter that records page excerpt, URL, publication date, ownership graph and human/physical verification, with a **blind** held-out question set.
3. Compare unresolved claims, cost per verification, source independence, false promotions, abstentions and calibrated reliability against both the original LLM and deterministic baselines.
4. Run local Ollama with the existing LAB008 output gate in a separate verification suite; report whether model acceptance itself improves or merely the reference system.
5. Keep code experimental until CI is green across all existing workflows and an independent reviewer checks the verification contract.
