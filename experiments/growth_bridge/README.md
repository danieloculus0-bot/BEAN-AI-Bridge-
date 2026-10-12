# Lab010: BEAN executes, learns, and adopts growth strategies

**Scope:** BEAN-AI-Bridge- synthetic-only experiment. **No money, no live Coinbase orders, no exchange credentials, no automatic live strategy deployment.**

## Run it

Linux:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_growth_sim.py' -v
PYTHONPATH=src python -m ezbean.growth_sim --train 300 --holdouts 100 --out ./growth-lab-output
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -p 'test_growth_sim.py' -v
python -m ezbean.growth_sim --train 300 --holdouts 100 --out .\growth-lab-output
```

The command produces `results.json` (scores + two complete action ledgers) and `adopted_policy.json` (the persisted learned action-value table). Both are mock receipts; keep runs in a scratch directory.

## The important part: adoption means actual simulated execution

Each decision uses only previous mock price returns to classify a context. A learned contextual bandit chooses among momentum, reversal, three-period trend, buy/hold and cash, deciding the *executed mock position*. The simulated order path changes position, charges a modeled 7 bps whenever exposure changes, computes net equity, records the chosen policy and realized reward, and then updates the chosen action's value. Failed actions receive negative realized rewards. There are no hand-coded context-to-winning-strategy labels and no reward computed from unseen future returns.

Training uses 300 simulated episodes drawn with deterministic seeds 10000-10299. The policy is written to disk and **reloaded** before 100 never-trained seed episodes 800000-800099. The frozen adopted learner is measured against an unchanged, completely untrained version and each of the five constant strategy choices using identical mock worlds and fees. The strongest constant comparator is reported conservatively using its hindsight average on the entire holdout; the learner never trains or chooses on that comparator.

`results.json` includes paired bootstrap 95% intervals for improvement. Positive *synthetic* acceptance requires the *lower* 95% bounds versus the untrained policy and the strongest fixed comparator to exceed zero. GitHub Actions repeats the test and benchmark independently on Windows and Linux, uploads receipts and fails if the synthetic acceptance gate fails.

## What it does NOT establish

The generator intentionally contains only five simplistic, cyclically shifting hidden regimes and has unrealistic statistical structure. Seeds are held out, but the underlying world families are not. A positive result means this bandit learned to adapt strategy selection **within this designed toy task**, not that crypto trading is profitable, that the agent has self-improved its training algorithm, or that a new neural checkpoint was trained.

BEAN Core's own reward/memory engine is a separate project; this module is an interoperable experimental Bridge component, **not** evidence that BEAN Core or a running AIscend instance has adopted these policy weights. Next scientific gate: add adversarial regime distributions, genuine unseen market data with forward-only timestamps, multiple independent model seeds, paper brokerage reconciliation, and no-memory/placebo/locked-policy ablations before promoting anything to real trading.
