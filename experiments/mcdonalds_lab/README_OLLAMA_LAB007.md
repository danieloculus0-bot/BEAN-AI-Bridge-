# BEAN Lab 007: local Ollama evidence reviewer

**Experiment, not a deployed search engine or a forensic lab.**

The prior BEAN Lab 005/Investigation 001 experiment recorded 20 McDonald's-food rumors, source metadata and analyst summary notes. Lab 007 connects that source ledger to a **real locally executing Ollama LLM**, using Python in an isolated `.venv`.

The architecture is:

1. **BEAN Core / Lab 005** performs evidence-attention checks, estimates uncalibrated support signals, tracks source-origin diversity, and reranks metadata.
2. **Ollama** reviews the supplied ledger's analyst notes for each literal claim and returns a skeptical counter-assessment, cited IDs, and a next falsification check.
3. **A deterministic validator** rejects fabricated source IDs, missing fields, missing model binaries, non-JSON responses and external Ollama hosts.
4. **The audit output** keeps separate BEAN and LLM columns. Neither model's statement gets recorded as independent verification.

The data set contains URLs and **researcher-written claim-level summaries**, not authenticated article bodies or direct lab records. Therefore this is a test of an LLM-based *evidence-review component*, not independent investigation. Add retrieval of actual source text, provenance authentication, blind adjudication and external verification before treating it as a fact-checker.

## Run in a BEAN Python virtual environment on Windows

Install [Ollama](https://ollama.com/download/windows), then download an actual model:

```powershell
ollama pull qwen2.5:1.5b
```

If Ollama is not already serving locally, open a separate terminal and run `ollama serve`.

```powershell
git clone --branch experiment/bean-ollama-verifier-lab007-20261010 https://github.com/danieloculus0-bot/BEAN-AI-Bridge-.git bean-bridge
git clone https://github.com/danieloculus0-bot/BEAN.git bean-core
cd bean-bridge
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pytest psutil
$env:PYTHONPATH = "$PWD\src;$(Resolve-Path ..\bean-core);$PWD"
python -m pytest tests -q
python -m experiments.mcdonalds_lab.ollama_verifier --model qwen2.5:1.5b --limit 20 --out lab007-live-ollama.json
```

## Linux/macOS venv

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pytest psutil
export PYTHONPATH="$PWD/src:$PWD/../bean-core:$PWD"
python -m pytest tests -q
python -m experiments.mcdonalds_lab.ollama_verifier --model qwen2.5:1.5b --limit 20
```

Pull a model and start Ollama separately before running the final command. Only `http://127.0.0.1:11434` (or another local loopback address) is accepted. Requires Python 3.10+.

## Automated verification

The branch workflow `.github/workflows/bean-ollama-verifier-lab007.yml` runs cross-platform Python venv tests. Separately, an Ubuntu runner installs an **actual Ollama runtime**, downloads `qwen2.5:1.5b` (~1 GB), and invokes all 20 claims. It uploads model output and service log as an artifact.

- The `tests/test_ollama_verifier_lab007.py` HTTP fixtures are **synthetic unit tests**, not a model run.
- The workflow job `ollama-live` provides the **real model run**.
- Each result has `status=llm_review_unverified` even if the LLM says `supported` or `refuted`.
- `reviewed` counts syntactically valid, source-cited outputs, not verified facts.
- `bean_signal_UNCALIBRATED` is a ranking heuristic, not a truth probability.
- Inference happens locally; Ollama does not itself search the Internet.

## Next test

Implement read-only browser/source retrieval (hash, publication date, quote span and URL), pass those excerpts rather than analyst-written verdicts, challenge LLM outputs with alternate sources and independently score calibration.
