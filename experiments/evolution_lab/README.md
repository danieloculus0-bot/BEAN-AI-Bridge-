# BEAN Evolution Lab 001

An isolated, reproducible, **synthetic** functional-awareness-proxy experiment built around the actual `bean.cognition.attention.AttentionFilter` from the separate [BEAN core](https://github.com/danieloculus0-bot/BEAN) project.

Research branch: `experiment/bean-evolution-lab-20261009`.
Core dependency branch: `experiment/bean-capability-lab-20261009`.

Neither repository's `main` branch is changed by this study.

## What this does

A simulated agent receives two noisy binary sensor readings each step. It starts with a stored belief about its environment, notices discrepancies, uses BEAN's attention filter to decide what deserves investigation, and can spend a limited budget on a ground-truth verification. A verified contradiction can revise its stored belief. A simulated process interruption exercises save/restore of verified state. Two bounded evolutionary searches mutate attention thresholds, required corroboration, verification budgets, question promotion, and learning from earlier false inspections.

The agent does **not** see ground truth unless it requests a bounded verification. The evaluator separately owns the scenario truth and rewards detection while penalizing delay, needless investigations, and false probes. Training and evaluation use disjoint reproducible seeds. Evolution can select parameter mutations but cannot rewrite the evaluator.

## What this does not do

- Does not demonstrate AGI, subjective awareness, sentience, consciousness, free-form curiosity or unsupervised source-code generation.
- Does not provide a secure sandbox for arbitrary untrusted executable mutations. Mutation is currently confined to typed parameters. The held-out seeds are separated by the evaluator, not secret against malicious code.
- Does not actuate hardware, access real ERP records, use API keys, invoke trading, or connect to the network from BEAN's simulated agent.
- Does not prove persistent BEAN SQLite cognition in the agent itself: agent save/restore is an explicit structured snapshot. Core BEAN SQLite continuity is tested separately in the BEAN repo.

## Results of initial phases (2026-10-09)

First lineage: six generations; 60 training episodes; 80 held-out episodes. The selected threshold 0.45, two consecutive confirmations, and two investigation permits achieved 100% recall in the standard environment (59 changes/80 episodes). It **tied the hand-tuned fixed comparator** exactly. Its holdout recall fell to 72.88% with correlated sensor faults and 57.63% with delayed sensors.

Mixed-environment lineage: searches on new training seeds with standard, common-mode sensor fault, and delayed sensor profiles. The selected configuration improved recall on the held-out correlated-fault profile to 86.44% and delayed-sensor profile to 66.10%, with standard recall still 100%. **This required substantially more verification probes and false alarms.** The mean fitness score on delayed sensors and standard sensors was lower than the fixed comparator, demonstrating an unresolved precision-versus-recall tradeoff. The selected lineage did not enable the experimental self-correction bit, which is why we added an ablation rather than claiming it had learned that behavior.

The final run adds an explicit ablation that flips the self-monitoring rule and measures its effect without re-selecting a winner. No favorable results are presupposed.

## Reproduce locally

In a common directory:

```bash
git clone -b experiment/bean-capability-lab-20261009 https://github.com/danieloculus0-bot/BEAN.git bean-core
git clone -b experiment/bean-evolution-lab-20261009 https://github.com/danieloculus0-bot/BEAN-AI-Bridge-.git bridge
python -m pip install pytest psutil
cd bridge
export PYTHONPATH="$PWD/src:$PWD/../bean-core:$PWD"
python -m pytest tests -q
python -m experiments.evolution_lab.bridge_evolution --out evolution-report.json
```

For PowerShell set `$env:PYTHONPATH = "$PWD\src;$PWD\..\bean-core;$PWD"` before running the commands.

See GitHub Actions `BEAN Evolution Lab synthetic benchmark` on this branch for the exact execution log and attached JSON evidence.

## Next development gates

1. Add source-specific reliability and calibration over time, measured against adversarial source behavior.
2. Separate hidden evaluation into an independently held private grading process before allowing arbitrary code-writing mutations.
3. Test detection across domain shifts and tasks that are not all binary state changes.
4. Replace snapshot-only continuity with BEAN's persistent memory events and audit lineage in the next integrated generation.
5. Add falsification, competing hypotheses and evidence provenance as experimental actions, not just names on a dashboard.
