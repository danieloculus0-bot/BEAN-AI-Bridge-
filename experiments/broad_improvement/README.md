# BEAN Lab 012 | Broad Self-Improvement Falsification

Research only. This is **not** a deployed self-modifying intelligence.

## Research question

Can one bounded policy trained to allocate verification attention across unrelated task types improve on a frozen baseline on new data, tolerate environmental shifts and *transfer to a withheld task family*? We count regressions, not just successes.

## Protocol

Four distinct synthetic domains: uncertain physical sensors, incomplete manufacturing ERP evidence, duplicated information sources and software-release anomalies. Each episode has 12 observations, of which only three may be inspected. The evaluator alone holds ground truth; useful investigations earn +3, false investigations cost -2 and missed positives cost -3. Every policy receives the same observations and inspection budget.

A frozen baseline uses four weights (4,2,1,1) for surprise, contradiction, coverage gaps and source-echo risk. Six generations of bounded mutations select four shared weights using only training seeds 1000-1039. We evaluate on disjoint ordinary holdout seeds 21000-21079, and changed-conditions seeds 30000-30079. Four additional leave-one-domain-out adaptations train on three task families and test on the fourth.

We call improvement demonstrated in this limited synthetic lab **only** when (1) aggregate ordinary holdout gain is positive and each domain loses no more than 0.25 reward/world; (2) aggregate shifted gain is nonnegative and each shifted domain loses no more than 0.75 reward/world; and (3) aggregate withheld-domain transfer is positive with at least three nonnegative domains.

## Initial local experiment results (synthetic)

Selected weight vector: (4,2,3,4). Reward change per world against frozen baseline:

| Domain | Ordinary held-out | Changed conditions | Leave-one-domain-out |
|---|---:|---:|---:|
| Sensors | -0.1 | +2.8 | -1.3 |
| ERP evidence | +4.0 | -0.5 | +0.6 |
| Source provenance | +5.0 | -4.0 | +1.8 |
| Release verification | 0.0 | +0.5 | +0.1 |

**Verdict: BROAD_IMPROVEMENT_NOT_DEMONSTRATED.** The shifted provenance environment degrades sharply, and withheld sensors show negative transfer. Do not promote this policy to main based on training fitness.

The result above is from local execution of the candidate harness. Cross-platform CI and actual BEAN Core integration should independently verify it. The GitHub Actions workflow pins a reviewed Core revision and attaches JSON evidence.

## What integrates with BEAN Core

The real Core AttentionFilter processes 12 evidence-like synthetic events. Real SelfOptimizationGovernor records an evidence-linked, rollback-specified **proposal-only** record in disposable SQLite. No authority to execute or change deployed configuration is granted. Parameter search itself is research code in the Bridge, not autonomous source-code modification by BEAN.

## Limitations

- Four synthetically constructed tasks share binary investigation rewards and the same four input features. They are not independent real-world skills.
- Environment data and evaluator are in the accessible repository. Seeds are disjoint but not secret. An adversary can overfit the benchmark.
- Rewards and domain-specific feature distributions were chosen by researchers, not discovered by BEAN.
- This tests a bounded parameter optimizer, not open-ended recursive self-improvement or autonomous novel science.
- No live company ERP information, credentials, trading or actuator commands are used.

## Reproduction

With BEAN Core checked out at commit e1973e681b3e35905276e661a1ece51321f54d22:

    PYTHONPATH=".:src:../BEAN" python -m pytest tests/test_broad_improvement_lab012.py -q
    PYTHONPATH=".:src:../BEAN" python -m experiments.broad_improvement.lab012 --core --out lab012-report.json

The workflow runs on Linux and Windows and uploads machine-readable evidence including negative outcomes, precision/recall, false probes, adaptation history and transfer deltas.
