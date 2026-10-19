# BEAN audit repair and learning backlog (2026-10-19)

**Intent:** Restore BEAN's original thought-experiment architecture: cognition in
Core, independent reusable logic modules, and Bridge as the communication /
composition layer. New behavioral safeguards are **not** part of this phase.
Safeguard ideas go in comments for later evaluation.

## Implemented and tested in experimental branches

| Finding | Repair | Code / evidence |
| --- | --- | --- |
| Unrelated facts silently closed curiosity questions | Require explicit linked learned-fact event with `question_id`, preserving unrelated questions | Core draft PR #128, `bean/tests/test_learning_flow_regressions.py` |
| Structured observations absent from reasoning prompts | Carry event `data` through SQLite context and local Ollama prompt | Core draft PR #128 |
| Provider/parse failure falsely reported success | Align reported success with actual provider and parser status | Core draft PR #128 |
| Vocabulary filtering obstructed local reasoning prototypes | Disconnected vocabulary-only filter from Core local reasoning test path | Core draft PR #128 |
| Cognitive components lacked a common runtime | Core exports blocks; Bridge owns catalog, lazy loading, Scratch-style wiring, reward-based module choice | Core draft PR #129; Bridge draft PR #36 |
| Two direct MemoryStore instances could share one SQLite connection | Per-instance thread-local handles; preserve singleton lifecycle | Core draft PR #130; Windows/Linux full Core CI |
| Unknown reasoning provider silently became mock | Explicit provider selection error; no fake LLM output | Core draft PR #130 |
| Investigator `list(... )[:max_sources]` could materialize unbounded data | Incremental source consumption with `islice` | Bridge draft PR #37 |
| Source or verifier exception could erase entire trial | Persist partial observations and experiment-error receipt, then re-raise | Bridge draft PR #37 |
| Switching module revisions could reuse stale Python code | Code-source-specific module identity; explicit refresh test | Bridge draft PR #37 |
| Failed module calls left no learning signal | Durable failure history and negative outcome feedback; selection adapts across Bridge restart | Bridge draft PR #37 |

These are **software correctness and bounded learning demonstrations**, not
evidence of generalizable cognition or a new neural model. Existing Bridge
Lab010 policy remains separate and uses simulated rewards; nothing here spends
money or acts on real machinery.

## Remaining work, in useful increments

1. **End-to-end autonomous local experiment dispatch.** Existing curiosity,
   goals, drives, reasoning and Bridge modules must negotiate a task, choose an
   available local tool, observe a result and update future behavior without a
   human scripting each step. Currently module selection/feedback is callable,
   not independently goal-driven.
2. **Generalization tests.** Expand beyond hand-designed binary forecasts.
   Use new unseen task families, matched cold/memory/placebo comparisons, and
   repetitions. A successful deterministic sample is only an integration proof.
3. **Context relevance and metacognition.** Replace simple most-recent-three
   local prompt selection with recalled, relevant observations, including
   structured event data, without dropping contradictory evidence.
4. **Flexible experimental evidence/trust.** Allow provisional assumptions
   and experiments when independent corroboration is scarce. Do not confuse
   experiments with verified facts; compare strategies by outcomes. The
   current DefinitionLibrary and OutputGate still use rigid evidence rules.
5. **Goal follow-through.** Audit `goal_state` and tick handlers so approved
   experiment objectives actually result in chosen module calls and feedback,
   not just repeated proposals.
6. **Durable module/experiment trajectories.** Connect Core's memory journal
   with Bridge's module execution receipts, including failures, to support
   diagnosis and counterfactual replay; retain private data locally, not in
   public Git history.
7. **Code hygiene and architectural ownership.** Keep Core cognition,
   Bridge composition, specialized module internals and UI conceptually
   separate; remove duplicates only after existing behavior is preserved.
8. **Review identity/bootstrap lifecycle and other existing filters later.**
   This is an audit item, not authorization to introduce new executable
   restrictions. User-directed sandbox experimentation remains the focus.

## Branch topology

- Core `main` -> `fix/learning-flow-20261018` (PR #128) ->
  `feature/cognitive-blocks-20261019` (PR #129) ->
  `fix/audit-learning-reliability-20261019` (PR #130).
- Bridge `main` -> `feature/cognitive-blocks-20261019` (PR #36) ->
  `fix/audit-learning-reliability-20261019` (PR #37).

The branches are intentionally unmerged drafts. Bridge's audit CI fetches
the corresponding Core audit branch to exercise real cross-repository calls.

## Verification links

- Core audit CI: https://github.com/danieloculus0-bot/BEAN/actions/runs/39255332691
- Bridge audit workflow:
  https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/workflows/bean-cognitive-blocks.yml

A passing unit-test suite alone does not establish broader learned intelligence.
