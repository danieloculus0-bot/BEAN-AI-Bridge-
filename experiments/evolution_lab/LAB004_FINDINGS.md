# BEAN Lab 004: Can a belief about reliability become obsolete?

Date: October 10, 2026. Location: isolated research branch
`experiment/bean-model-revision-lab004-20261010`.

## Research question

Can BEAN recognize when prior evidence about an input source stops predicting
later independently verified observations, revise that model, and do so without
spending its entire investigation budget? This probes operational self-model
revision, **not subjective awareness or AGI**.

## Implemented

- Extends the actual BEAN AttentionFilter-driven experimental controller.
- Tracks likelihood of verified observations under its *previous* source trust.
- Requires two consecutive sufficiently unlikely verified outcomes to trigger
  a documented source-model revision, retaining the previous audit evidence.
- Can allocate a separate, seeded inspection opportunity without inspecting
  source readings or simulated truth to decide when that opportunity occurs.
- Retains trust and change-detection state across simulated restarts and episodes.
- Compares memories carried across 80 and 120 worlds against fresh memory.
- Reports mean task reward, detection recall, false probes, model revisions, and
  prediction-calibration error.
- Replays an explicit two-inspection correction into actual BEAN Core SQLite:
  BEAN's event logger, EpistemicGuard, Uncertainty Garden, Falsification Engine,
  and reasoning context all participate. The pilot records two verified events
  and two hypotheses; its context contains origin version 002.

## Baseline 004 study: 80 worlds for each of six environment sequences

An inspection *every episode* improved recall substantially but used far more
probes. It often reduced the task reward. A simple revision rule with **no
independent checks** caught few source changes because the agent's investigation
decisions were based on the same now-stale trust model.

For example, under **stuck sensor B → repaired sensor B**:

| Strategy | Change recall | Mean reward | Independent audits |
| --- | ---: | ---: | ---: |
| Keep old source trust | 80.00% | 2.1107 | 0 |
| Revise after 2 surprises | 81.67% | 2.2034 | 0 |
| Revise + audit every episode | 88.33% | 2.0599 | 77 |
| Fresh each episode | 85.00% | 2.3359 | 0 |

These are simulator measurements, not claims about real-world devices.

## Lab 004b: Train-only sparse independent audits

Compared independent-audit opportunities of 0%, 15%, 30%, 50%, 75%, and
100% per synthetic episode on seeds **51000–51039**. Maximizing the average
synthetic task reward across six training worlds selected **30%**.

We then evaluated the selected frequency on previously unused seeds
**62000–62119** (120 episodes per scenario, six scenarios, 720 episodes for
each strategy). This holdout was not used to select the audit rate.

| Strategy | Mean recall | Mean task reward | Mean Brier error |
| --- | ---: | ---: | ---: |
| Old trust, no revisions | 86.67% | 2.2900 | 0.1950 |
| Revision, no independent audits | 87.72% | 2.3355 | 0.1899 |
| **Revision + 30% independent audit opportunities** | **92.80%** | **2.4463** | **0.1686** |
| Revision + every-episode audits | 98.59% | 2.4260 | 0.1534 |
| Fresh each episode | 91.58% | **2.4886** | 0.1612 |

Scores and recall are averages over six environments, not confidence intervals.
Sparse audits struck a better task-reward tradeoff than constant auditing in
this holdout. **Fresh starts still scored slightly higher**, so carrying memory
has not demonstrated general superiority. Always auditing obtained highest
recall but at greater verification cost.

The metric tradeoff is real: no approach dominates precision, recall, expense,
and robustness across all scenarios. The 30% choice may still be sensitive to
the specific synthetic profiles and should be validated with more seeds and
richer, nonbinary tasks.

## Cross-system integration proof

A synthetic agent begins with source A deeply distrusted from historical
outcomes. Two independently verified surprises cause a change-point hypothesis.
The actual BEAN Core then stores the two verified observations and audits two
falsifiable hypotheses. The core reasoning context retains the canonical
origin record `BEAN_ORIGIN_COVENANT_002`.

This is more than in-memory toy state, but real deployed sensors, persistent
multi-session user-facing behavior, and actual autonomous inquiry are not yet
validated.

## CI

Workflow: `.github/workflows/bean-model-revision-lab004.yml`.
Tested with pinned BEAN Core commit `3cf85e63005d97ceaa7484b2d4d61efb0da3ee10`.
The final CI run provides test XML and both JSON reports for Linux and Windows.
No commits were made to BEAN or AIscend main during Lab 004.

## Next falsification tests

1. Use three or more sources with correlated faults and missing observations.
2. Separate reliability estimates based on *triggered* vs *randomly selected*
   verifications, correcting sampling bias.
3. Have the agent propose alternative source explanations and select the next
   most informative test, rather than merely triggering a fixed check.
4. Repeat evaluation across several independent random seeds, and include
   penalties for false confidence and overreaction to short anomaly bursts.
5. Only consider production promotion after data-format compatibility and
   independent regression verification.
