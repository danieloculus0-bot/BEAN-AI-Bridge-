# BEAN Remote Viewing Blind-Vault Experiment

This experimental branch adds a cryptographically sealed-target test to BEAN AI Bridge. **This is a research prototype, not a finding of paranormal ability or a deployed internet-secure vault.** Never commit secret targets, local vault files, passphrases or session credentials to public GitHub.

## Seven-stage experiment
1. CREATE: An operating-system cryptographic RNG creates four matched candidate descriptions in one randomly selected category (painting, vehicle, object, concept or geometry). One is randomly designated the target. The whole bundle includes a fresh 256-bit commitment nonce and is encrypted with AES-256-GCM using a scrypt-derived key.
2. PUBLIC COMMIT: Publish the public challenge.json commitment hash to an external, timestamped witness **before any observing session**. This prevents silently substituting the target later, if the witness is trusted.
3. SEPARATE CHAT: Start a clean unconnected session and provide only the ID and neutral viewing instructions. No target, target category, four options, keys, admin details or earlier transcripts. The new AI listens to and records the participant's observations, without interpreting a hidden target.
4. SEAL: Viewer submits the verbatim complete description and a persistent new-chat transcript reference via the viewer-only portal endpoint. Its SHA-256 is immutable by the ordinary API; externally timestamp the hash before reveal.
5. CLOSE: An operator independently confirms that the chat has ended and signs the explicit close attestation via the admin-only portal endpoint. The application CANNOT detect actual ChatGPT conversation closure by itself.
6. BLIND JUDGE: A distinct judge sees all four candidates in randomized order alongside the sealed observation, but not the correct index; their single choice is then locked before truth is revealed.
7. REVEAL: A distinct reviewer can access full bundle, actual target, commitment nonce, observation and scoring only AFTER the judge has sealed a choice. Independently validate commitment against original external hash and observation hash against the archived transcript.

## Locally run the prototype

Python 3.11+ required.

~~~sh
python -m pip install "cryptography>=42"
python -m experiments.remote_viewing.portal create experiments/remote_viewing/runs/trial001
python -m unittest discover -s experiments/remote_viewing/tests -v
~~~

During CREATE, choose a high-entropy passphrase and store it in a private password manager. The target never prints. Generate FOUR different bearer tokens privately, e.g. repeat:

~~~sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
~~~

Set the environment variables RV_VIEWER_TOKEN, RV_ADMIN_TOKEN, RV_JUDGE_TOKEN, RV_REVIEWER_TOKEN and RV_VAULT_PASSPHRASE without entering them into AI chats, GitHub or URL query strings. Start the local portal:

~~~sh
python -m experiments.remote_viewing.portal serve experiments/remote_viewing/runs/trial001 --port 8765
~~~

The server binds 127.0.0.1 only by default. **Never publicly expose its plain HTTP listener.** Any remote portal needs an authenticated TLS reverse proxy, external log witness, operational key custody, backups and security hardening beyond this prototype.

## Gated API

All POST requests use JSON and the proper role's Authorization: Bearer TOKEN header.

| Endpoint | Auth | Behavior |
| --- | --- | --- |
| GET /v1/challenge | Public | Only challenge ID, SHA-256 commitment and candidate count |
| GET /v1/status | Public | Sealed, closed and judged flags only |
| POST /v1/observation | Viewer | JSON with description and chat_reference; seals once and returns observation hash |
| POST /v1/close | Admin | JSON with chat_closed:true and observation_sha256; attests chat closure and seals once |
| POST /v1/judge-packet | Judge | JSON {}; returns observation and four candidates but never correct index |
| POST /v1/judge | Judge | JSON with selected_candidate_index (0-3) and judge_id; seals once |
| POST /v1/reveal | Reviewer | JSON {}; after judgement seal returns target, correct index, full verifiable commitment preimage and hit/miss |

The portal verifies original commitment at reveal; all ordinary immutable operations use exclusive file creation. Someone with OS-level ownership can still tamper with files. An independent timestamped witness is essential for strong evidence.

## BEAN logic (B/E/A/N)
- B / Blindness: No leaked target, category, choices or credentials. Otherwise EXCLUDE.
- E / Evidence: Externally committed target hash and observation hash, retained exact transcript. Otherwise EXCLUDE.
- A / Adversarial review: Independent custody, blinded judging, correct sequence, leakage and manipulation checks. Otherwise COMPROMISED.
- N / Null: Preregister independent sample size, exclusion rules, chance baseline of 1/4 and primary analysis. Do not infer paranormal causation from one match.

An exact one-sided binomial test is implemented in gate.py, but ONLY valid for the stipulated equal-choice independent null. A single hit is a 25% event by chance. Human judges, duplicate targets, feedback, correlated sessions and exploratory analysis demand additional controls.

## Limits
- Text-based categories are a finite test pool, not literally all possible objects or media. A future module could securely import third-party photos, sounds and texts.
- AI hallucination is not a guarantee of cryptographic randomness; selection uses OS CSPRNG.
- This is NOT deployed or ready for adversarial public use. Credentials must not be shared with the observing chat before closure.
- A hash makes substitution detectable, not globally impossible to fake. It does not prove the operator was blinded or the plaintext was never leaked.
- More stringent than some historical protocols is a **design goal**, not a measured superiority claim.

See research-notes.md for favorable, skeptical and modern research sources and the preregistration framework.
