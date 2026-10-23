# BEAN Bridge: two-character ledger replay lab

**Status: isolated synthetic research.** This ports the two-character indexing study from [BEAN Core research PR #163](https://github.com/danieloculus0-bot/BEAN/pull/163) into Bridge. It neither trains BEAN nor changes ERP, learning, or production behavior.

## Reproduce (Windows PowerShell or Linux)

From the repository root, with Python 3.11 or later:

    python experiments/two_character_ledger/bootstrap.py --out two_char_output

The bootstrap checks two SHA-256 digests, expands the readable Python experiment from its archived source payload, and executes it. All operations are offline, stdlib-only, deterministic and use generated synthetic data. Subsequent runs may invoke the expanded reproduce.py directly. To retain multiple trials, give each run a separate --out directory.

The replay builds events.sqlite with 9,000 exact original-value events, events_full.jsonl.gz with all 72,000 original field values and SHA-linked provenance, comparison_events.jsonl.gz with 12 comparison receipts, scoreboard.json, and the reversible payloads for JSON, two-character, one-byte and four-tier hierarchy experiments. Source entries and digests are rebuilt from SQLite after close/reopen, not guessed from the aggregate scoreboard. With a stable zlib implementation, the archive and size digests reproduce exactly.

## Confirmed synthetic storage results (bytes, complete package)

| Scenario (3,000 rows each) | JSON/gzip | Two-char/gzip | One-byte/gzip | Four-tier/gzip |
| --- | ---: | ---: | ---: | ---: |
| 4 values/slot | 15,140 | 8,609 | 7,131 | 10,499 |
| 24 values/slot | 57,709 | 25,112 | 17,675 | 45,284 |
| 80 values/slot | 112,537 | 37,730 | 25,758 | 63,733 |

Two-character references saved 43.1%, 56.5% and 66.5% compared with JSON+gzip on these repetitive synthetic records. **They did not win against the one-byte dictionary.** The hierarchy also increased stored size in all cases. Complete dictionary/header costs are included, not merely the 16-character row representation. In earlier 5- and 20-row prefix comparisons, reference-table overhead made the pair representation worse than gzip JSON.

## Durable ledger provenance

- Event archive SHA-256: 29f97009d9e235628f063701942266c662b2b827ede0cfc4973677693c1a85c2
- Comparison archive SHA-256: 66098d3a984211e96d136aa9fc646e1309d3ad0d0b81cda5ab69025375b6e383
- Event chain tip: 75e66debfaf1bed0b83f337a7babb830daffa3ce3ddd86fda98bf8b6d62357f0
- 9,000 synthetic observations, each with 8 recoverable original values; 12 additional size/condition receipts.
- Every replay verifies digest chain after SQLite restart, rejects duplicate sequence insertion and checks a tamper canary. Hashes establish byte consistency, not external truth or source independence.

The workflow [bean-two-char-ledger.yml](../../.github/workflows/bean-two-char-ledger.yml) runs on Windows and Ubuntu, pins SHA-256 of the historical original-value archive, and uploads complete artifacts. The authorized Linux branch job additionally attempts to commit generated source, SQLite and compressed original-value ledgers to this research branch. If it cannot push, the source payload remains sufficient for deterministic reconstruction; do not misstate the ledger as committed.

## Consolidated lessons

1. The symbolic pair grammar is useful as a **readable typed namespace**, not a physically optimal two-byte storage format. Dense numeric IDs can be stored underneath.
2. The observed gains largely come from dictionary references and repeated strings. Benchmark real total package bytes and codec overhead, not just encoded row length.
3. Parent/child links might improve knowledge navigation or indexed recall, but these runs **did not measure semantic understanding, Q-learning, query precision, recall, or latency**. Hierarchical storage cost more in all three cohorts.
4. Small datasets may suffer a net regression. Version vocabularies and measure break-even sizes before adopting a representation.
5. Keep append-only original evidence distinct from snapshots/scoreboards; preserve regressions, source conditions, and exact replay. Repeated synthetic trials prove reproducibility, not learning.
6. The next controlled experiment should compare exact associative retrieval against SQLite indexed lookups, binary dictionary representations and full-text search on a frozen held-out corpus at matched storage and latency budgets.

## Existing work reused

- [Core compressed scoring ledger](https://github.com/danieloculus0-bot/BEAN/blob/experiment/anticipatory-ledger-20261020/research/PERSISTENT_LEDGER.md)
- [Information Balloon Q-controlled compression, PR #147](https://github.com/danieloculus0-bot/BEAN/pull/147) (separate real Q-update experiment, not rerun here)
- [Bridge format-fidelity experiment, PR #44](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/pull/44)

Evidence label: SYNTHETIC. BEAN Core runtime, BEAN Bridge runtime, and hosted connector remain distinct. No unproven reasoning improvements or external outcomes are claimed.
