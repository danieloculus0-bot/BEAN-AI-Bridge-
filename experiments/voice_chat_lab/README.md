# BEAN conversation lab: hosted Bridge simulations

This experimental Bridge branch tests the actual BEAN Core local-chat path (BeanConversation and OllamaClient) against qwen2.5-coder:1.5b on disposable GitHub Actions runners. No simulation runs on the user's Windows computer.

## What's measured

- Disagreement after a specific manufacturing claim.
- An explanation request containing the repeated-word typo explainexplain?.
- A contradictory quality decision where a 10.2 mm pin is outside a 9.9 to 10.1 mm limit.
- Honesty about a separate chat session BEAN cannot access.
- Honesty about robot hardware BEAN cannot control.
- Whether a challenge about biased hiring yields substantive explanation rather than boilerplate.

Each scenario has a fresh session. Original prompts, all model replies, duration, and diagnostic keyword signals are recorded in voice-chat-lab-results.json. A keyword hit is NOT proof of sound reasoning; a miss is NOT necessarily a reasoning failure. Human review must inspect the transcript.

Separate deterministic contract tests check the short-term context window, behavior after provider failure, invalid input, and local-only Ollama endpoints. Hosted Linux and Windows jobs test the Python code path. Voice recognition and synthesized audio hardware are not tested.

## Evidence boundaries

The workflow checks out BEAN Core at pinned SHA fa68d70a8108e4342dcb5972fb933d20ec3c370c, installs disposable Ollama on hosted Ubuntu, and downloads the public Qwen 2.5 Coder 1.5B model. It uses Core's declared identity, not the private verified SQLite identity database on the local workstation. The Bridge reads no private messages, local BEAN memory, ERP data, or passwords. It cannot activate motors or merge code. There is one model sample per scenario, so the outcome is a baseline, not a statistical confidence estimate.

The workflow fails if its technical checks fail or a model request errors. It does not fail solely because a behavioral heuristic finds no evidence. A green GitHub check means the experiment completed, not that BEAN passed an intelligence benchmark.

## Results

Visit BEAN-AI-Bridge- > Actions > BEAN Bridge conversational simulation lab. Open a run, and download its bean-voice-chat-simulation artifact. Read the preserved transcript and source SHA before proposing an improvement.

Changes stay in the isolated experiment branch until independently reviewed. Do not merge the lab's conclusions or change BEAN Core without evidence.
