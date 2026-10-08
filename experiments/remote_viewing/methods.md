# Experimental Methods: BEAN no-frontload, two-pass protocol

This document specifies proposed experimental techniques, NOT evidence that they work. Pre-register before trials. The implemented blind vault is a gatekeeping prototype; it does not currently assign experiment arms automatically.

## Comparison arms

A. Unstructured free-response control: participant receives only opaque challenge ID and ten minutes to record impressions in any order.

B. CRV-inspired sensory protocol: within the same ten-minute duration, participant records immediate overall gestalt, then geometry, color, texture, motion, spatial relationships, emotional content and suspected concept. Unlike some training protocols, the operator and AI facilitator are fully blind and provide no feedback. Do not teach or claim Ingo Swann's original protocol is implemented exactly.

C. Proposed BEAN Two-Pass Zero-Frontload method:
  - Pass 1 (first 3 minutes): raw immediate impressions and sketches; no naming objects, no target-domain speculation, no AI discussion or suggestions.
  - Pass 2 (next 4 minutes): geometric relationships, sensory associations, anomalies, distinctive combinations, confidence for each observation. Preserve contradictions rather than smoothing them away.
  - Lock stage (last 3 minutes): viewer reads Pass 1 and Pass 2, records a final uncued free-form report without changing either original pass, explicitly flags speculative nouns, then seals all three sections.
  - AI acts as recorder, not interpreter, coach or source of cues. No search/tools/shared memories while acquiring observations.

## Comparative design

Randomize independent trials to arms A/B/C using a pre-committed randomization schedule concealed from evaluators. All use identically generated blinded target pools, equal duration, separate new chats, independent target custody and the same four-candidate blind scoring. Archive raw timestamped responses and all failures. Measure target match rate as primary outcome. Secondary exploratory measures: judge inter-rater agreement, amount of distinctive detail, false-positive rate against decoy-only and unrelated-session negative controls, dropouts and reviewer calibration.

Comparing multiple protocols after seeing results inflates false positives. Define an overall primary contrast in advance, adjust for multiple testing, predefine sample size and exclusion criteria, and replicate on a held-out pool with entirely new judges. A 4-way success chance of 25% is not proof that human semantic judges act as independent equal-probability random selectors: empirically validate candidate exchangeability with negative controls.

## Stronger delayed selection extension (NOT YET IMPLEMENTED)

As a separate precognition-focused arm, choose and encrypt an entire four-target pool BEFORE the observation but do NOT designate the real target yet. Seal participant description and independent witness timestamp FIRST. Then use a future public cryptographically verified randomness beacon round to select the true target index, with the beacon round and selection function committed in advance. Reveal only after the same closing and blind judgment gates.

No custodian can leak the true target beforehand if the beacon is genuinely unpredictable and the selection protocol is enforced. However, this probes claims about knowledge of FUTURE outcomes, not just perception of a currently fixed target. It is **not** the same experiment as the initial sealed-target protocol and should be reported independently.

## Required blind-vault hardening before real-world claims

Independent custody; external timestamped challenge and observation commitments; authenticated TLS hosting; server security review; single-use credentials; tamper-evident external logs; fully isolated AI memory and search; no target pool hints; anti-replay; no target duplicates; blinded independent human judging; and confirmatory replication. None of these can be replaced by model confidence or a claimed "100% foolproof" procedure.
