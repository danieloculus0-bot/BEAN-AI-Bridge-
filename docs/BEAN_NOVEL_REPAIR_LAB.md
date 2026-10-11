# BEAN novel code-repair laboratory

The original Bridge self-improver demonstrated two changes using fixed templates. This lab tests a harder threshold: BEAN calls a real hosted model to propose an unfamiliar source change, independently verifies the exact bytes on Windows and Linux, and submits only passing work to code review.

## First case: Midnight RMA Paradox

The immutable red-test oracle lives in [Bridge challenge PR #19](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/pull/19), pinned at commit 75b12233c243b61c61b2f9b205951cb8ae45f4b7. Equivalent cutoff instants currently change RMA counts and can create a false zero even when source completeness is asserted. All fixtures are synthetic and public-safe.

## Separation of responsibilities

1. Generator: Checks that the ordinary Bridge baseline passes and the separate oracle fails. Sends the full current source and sealed oracle to GitHub Models, which proposes complete replacement source for src/ezbean/core.py. Syntax, hash, and change-size checks run here. Model code is NOT executed during this stage.
2. Validator: Separate Linux and Windows CI jobs check immutable source and test hashes, reproduce the failing baseline, then execute the model candidate against the entire existing suite plus the untouched external oracle. Failures are preserved; changes are rolled back in the test checkout. These jobs have no model token and no GitHub write permission.
3. Publisher: Only after BOTH platform checks pass, another CI job packages exactly the reviewed source and original oracle on a new branch and attempts to open a PR. It cannot auto-merge to main.

The generator, verifier, and publisher are distinct jobs with separate GitHub permissions. CI runners have network access and are NOT complete security sandboxes; code reviews remain mandatory.

## What must be true before success can be claimed

- The code was proposed by a hosted model; not one of BEAN's old two hard-coded patches.
- Both independent runners confirmed clean original tests and failing original challenge.
- The produced candidate passed all existing tests and the original challenge unchanged.
- Evidence includes pinned commits, source digests, CI receipts and a reviewable source PR.
- Follow-up withheld tests probe additional timezones, daylight savings, completeness and site-calendar policies. Passing this synthetic test does not establish official ERP reporting correctness.

The workflow runs on GitHub Actions schedule daily and on manual dispatch, plus when its own source is promoted to main. It uses GitHub Models with workflow models:read permission, default openai/gpt-4.1. Provider eligibility, rate limits, availability and costs are controlled by GitHub. If unavailable, receipts record failure. No provider call success is claimed before actual CI evidence.

Research caveat: this is the first model-backed novel repair pipeline, not demonstrated general self-programming, self-directed issue discovery, or persistent multi-model intellect. Keep the existing red-only challenge PR unmerged.

## Local test command

PYTHONPATH=src python -m unittest discover -s tests -p test_bean_novel_repair_lab.py -v

These are deterministic protocol tests; no model key or external service is needed.