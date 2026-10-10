# BEAN Evidence Intelligence Lab 003: verification and memory results

Date: 2026-10-10. Status: isolated synthetic experiment; **not merged to main**.

## Evidence

- GitHub Actions full Bridge regression and real BEAN Core integration: **52 tests passed**.
- Latest runner: https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38028682960
- JSON and JUnit evidence are attached to the Actions run.
- Core dependency pinned to reviewed and merged commit `3cf85e63005d97ceaa7484b2d4d61efb0da3ee10`.
- In the integration replay: verified events, BEAN epistemic audits, unresolved Uncertainty Garden records, Falsification Engine results, and a reasoning context packet are actually persisted via the real BEAN core.
- The reasoning packet now correctly includes origin covenant `BEAN_ORIGIN_COVENANT_002`.

## Changes delivered

- A bounded experimental verification agent that learns A/B sensor reliability only when it explicitly requests an independent inspection.
- A self-reporting evidence trail containing the prior belief, raw observations, verification outcome, and source reliabilities.
- Competing and falsifiable hypotheses, including possible shared sensor failure.
- JSON-safe snapshot/restart of beliefs, source reliabilities, open hypotheses and investigation history.
- Fixed an attention gate deadlock: a new discrepancy can trigger an investigation even when there was no previous hypothesis and no scheduled check.
- Extended the simulator with unseen sensor drift, stuck sensors, early changes and late changes; a direct fixed-controller comparator and ablations.
- Longitudinal source-model carryover across 80 separate episodes, with midstream environmental regime changes.

## Final Lab 003 held-out comparison (80 episodes per condition)

| Condition | Fixed Lab 002 recall | Evidence Lab 003 recall |
| --- | ---: | ---: |
| Standard | 100.00% | 98.21% |
| Correlated noise | 76.79% | 73.21% |
| Delayed sensors | 62.50% | 67.86% |
| Drifting sensor A | 7.14% | 78.57% |
| Stuck sensor B | 7.14% | 83.93% |
| Unexpected early change | 100.00% | 100.00% |
| Unexpected late change | 76.79% | 73.21% |

The Lab 003 candidate was selected on distinct training seeds. Its selected policy does **not** use a periodic inspection clock. These are recall figures only; neither perfect calibration nor universal superiority is demonstrated.

## Longitudinal holdout (80 episodes)

| World pattern | Persistent-reliability recall | Fresh-model recall |
| --- | ---: | ---: |
| Stable drifting A | 83.33% | 83.33% |
| Stable stuck B | 93.33% | 93.33% |
| Stable standard | 98.33% | 98.33% |
| Stuck B, then normal | 91.67% | 96.67% |
| Normal, then stuck B | 95.00% | 95.00% |

Retention modestly improved some total fitness scores and lowered probe use, but **hurt after a formerly bad sensor recovered**. Example: drifting A mean score increased from 1.6198 (fresh) to 1.7253 (persistent); stuck B to normal decreased from 2.8188 (fresh) to 2.5539 (persistent). Source reliabilities were sometimes driven to extremely confident values from selectively sampled verification events; this is a calibration and change-detection issue, not proof of intelligence.

## Scientific limits

- All stimuli are synthetic and use a bounded simulated ground-truth inspection action, not a real-world independent oracle.
- No live robot sensors, actuators, model API, or ERP data were used.
- The source-reliability algorithm is an experimental controller added to the Bridge; the core's existing AttentionFilter and cognitive memory modules are real.
- Verification samples are not random: the agent usually asks when it is suspicious. This creates selection bias in source accuracy estimates.
- Fixed binary scenarios do not establish AGI, subjective awareness, or independently discovered conceptual knowledge.
- Never use this branch to drive hardware or certify operational safety.

## Recommended next iteration

1. Introduce a change-point detector that explicitly tests whether previously learned source reliabilities still hold, with hysteresis to avoid overreacting to one noisy sample.
2. Counter verification-selection bias using planned independent calibration samples that are not timed to known scenario changes.
3. Compare online model resets, slow decay, fast decay and fixed source priors on fully held-out regime shifts.
4. Evaluate reliability on tasks with richer states and real multi-step hypothesis selection, not only a binary value.
5. Preserve the unsuccessful experiments and ablation results; do not selectively present only recall improvements.

This is a research branch, **not ready for merge to main**.
