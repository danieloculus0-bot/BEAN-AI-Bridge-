# AIscend strategy and narrative evidence

The complete collection lives in the companion [AIscend strategy research branch](https://github.com/danieloculus0-bot/AIscend/tree/research/strategy-atlas-20261024/research/strategy_atlas). It contains 289 algorithm specifications, 75 source records, 27 dataset contracts and an attributed historical database. Negative findings and failed/inconclusive experiment outcomes are retained.

This bridge change adds a standard-library adapter for `aiscend.bean.research_context.v1` packets. It validates the payload checksum, research-only scope, as-of time and every included document's publication/first-seen/availability relationship. It stores the packet in a separate append-only SQLite market-research ledger, with recall limited to packets that had actually been ingested before the requested decision time. It does not place financial research into ERP KPI records.

The included `BEAN_CONTEXT.json` is a real exported packet from 105 captured headlines across four publishers, with a bounded evidence list, themes, named asset evidence, positive/negative polarity and candidate algorithm IDs. This is a lexicon-based headline extractor. It is not a trained model or a demonstrated profitable policy. Attention-surprise features remain unavailable until a prospective baseline exists. A checksum demonstrates payload consistency, not the truth or independence of news claims.

Run from the Bridge repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_market_research.py -v
python tools/aiscend_research_context.py --context research/aiscend-strategy-atlas/BEAN_CONTEXT.json --ledger artifacts/market-research.sqlite3
```

The corresponding workflow imports the actual packet and archives the resulting research ledger. Context ingestion is advisory evidence handling and cannot authorize a trade or change a strategy implementation.

To retrieve algorithms or historical values, use `src.strategy_atlas.Atlas` in AIscend. The SQLite database includes per-asset compressed streams for 1,953,796 asset-day records across 2,235 assets; 1,603 assets have one or both USD price fields. Per-asset histories vary, inactive and non-crypto instruments may occur, and no execution eligibility is implied. The Coin Metrics data is CC BY-NC 4.0; commercial rights are not established. See the source package for provider licenses, dataset availability, negative evidence and precise implementation limits.

`integration_manifest.json` pins the accompanying code/data revision and checksum. The context also works as the observation payload for the existing AIscend `observe_with_current_bean` interface. This task verifies serialization, timestamp handling and durable recall, not an actual language-model inference or profitable trading test.
