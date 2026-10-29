# BEAN Metamorphic Defect Discovery Lab

BEAN's engineering intelligence must include the ability to **find problems we did not manually enumerate**, rather than merely apply preapproved patches or overfit tests already shown to a model.

This Bridge lab runs a bounded, deterministic, dependency-free **synthetic ERP invariant explorer**. It is a new discovery instrument, not a model or AGI proof.

## What gets tested

Each run generates synthetic reporting events across jobs, RMAs and production and independently checks:

- A single physical cutoff instant, expressed in different valid ISO-8601 timezone offsets, should yield the same evidence and KPIs under the generic reporting calendar policy.
- Shuffling observations cannot change an evidence-based report.
- Re-encoding an observation's timestamp in another timezone cannot change its eligibility or selected entity.
- Source coverage assertions are preserved as separate evidence, not authenticated by the lab.

The random seed, generated synthetic events, cutoff representations, observed before/after KPI values, invariant names and affected domains are preserved in a SHA256-bound JSON receipt.

**A finding is not a proven root cause**, and a source-asserted complete snapshot is not an authenticated complete snapshot. Calendar normalization must follow a documented UTC or explicitly configured site-local policy. The synthetic probes never contain an employer records or customer information.

## Separation of roles

This lab is the **Bridge discovery and witness lane**. Core [Lab019](https://github.com/danieloculus0-bot/BEAN/pull/37) is separately developing persistent code-writing, candidate archives and iterative learning. Core [Lab017](https://github.com/danieloculus0-bot/BEAN/pull/33) tracks cross-session peer messages. BEAN should take an exported witness, select/rank an improvement, author new code with the optional model-backed author, and give the unchanged synthetic case to a separate validator. Nobody edits another session's branch.

This addition does not change Core or the original Midnight challenge, and does not merge repairs automatically. Linux and Windows GitHub Actions run the same randomly seeded inputs in parallel and preserve their evidence independently. It is scheduled daily, and can be manually dispatched.

## Reading results correctly

The reporting job returns success when it **successfully completes discovery**, even if its machine-readable status is `FINDINGS_REQUIRE_PEER_REVIEW`. A green discovery workflow is **not** proof the code under test passed its invariants. The summary and uploaded evidence must be read. The Python CLI has `--fail-on-finding` for use as an actual acceptance gate later.

You should evaluate increases in proven general autonomy using: genuine new defect families found, fraction reproduced by independent observers, model-authored novel patches passing sealed tests, recovery after CI failure, lessons retained across unrelated code bases, and net utility per human intervention. No numeric quality-score increase is implied merely by installing an explorer.

## Local commands

From the Bridge root, Python 3.11+, no network or tokens:

    PYTHONPATH=src python -m unittest discover -s tests -p test_bean_metamorphic_hunter.py -v
    PYTHONPATH=src python tools/bean_metamorphic_hunter.py --seed 20261010 --trials 60 --receipt .bean-hunter/evidence.json

All observations use `synthetic_meta_erp` and a fixed simulated October 2026 reporting window. CI uses the immutable run ID as the seed so the experiment explores different combinations across days but can always be exactly replayed.
