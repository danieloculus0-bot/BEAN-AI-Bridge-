# AIscend / BEAN — simulated crypto trade Q-learning on a compressed ledger

**Research only.** This experiment executes the **actual AIscend BEAN adaptive growth Q-policy** at pinned AIscend source `27e72a340e3a3437b3bee1c781c809941806a79d`. It is not a stub strategy, hosted BEAN Core integration, profit guarantee, wallet connection, order execution or trading recommendation.

## Purpose

Test whether a printable two-character reference codebook can organize the actual Q policy's decision history while preserving all trade observations, evolving account equity and Q-state receipts. Storage compression is independent from policy profitability.

## Reproduction

From this Bridge research branch, check out the pinned [AIscend](https://github.com/danieloculus0-bot/AIscend) code into `_aiscend` (GitHub Actions does this automatically). Then:

    python experiments/crypto_trade_ledger/run.py --aiscend _aiscend --out crypto_evidence

Runs with Python 3.12, standard library only; Windows PowerShell and Linux. GitHub Actions [workflow](../../.github/workflows/bean-crypto-compressed-ledger.yml) verifies both OSes and publishes a complete archive. Each fresh `--out` directory retains its own immutable evidence; rerunning an existing directory removes the previous local database, so choose a new directory to preserve it.

## Exact test scope

- 4 deterministic, **synthetic** market regimes: `uptrend`, `downtrend`, `sideways`, `trend_reversal` (contains market shock days). No recent Coinbase or other actual prices are claimed.
- 12 fixed seeds × 4 independent markets (BTC, ETH, SOL, DOGE) × 4 regimes × 240 consecutive five-minute bars = **46,080 original observations across 192 independent paths**.
- **$1,000 independently per path**, not $192,000 invested in one portfolio. The Q strategy's warmup is 160 bars and forward online phase 80 bars. Q updates are the actual AIscend `_apply_bar` calls, not synthetic invented rewards. Those returns and trades are **simulated hypothetical positions**.
- BEAN growth policy is genuinely reward-adaptive and causally uses previously closed candles. Learning continues during the forward phase; it is not a frozen-policy holdout. Fixed controls include same-market buy-and-hold and cash, under the same AIscend growth module's 0.07% change-cost assumption.
- Separately run AIscend's **existing multi-asset historical backtest** for cash, buy-hold BTC, momentum, and persistent policy families at the research module's 0.6% per-side cost stress. This is **not** directly fee-comparable with the 0.07% learner; the groups are reported separately.
- No live market prices, Coinbase orders, verified exchange fills, live balances, model-weight updates, portfolio aggregation, or real-world profitability are asserted.

## Printed decoder

Every original event contains market, regime, Q action, and exposure. A printable `paper_decoder.txt` lets a person decode codes without hexadecimal tools. The string `M1R2A3P1` means `BTC-USD / downtrend / trend_3 / LONG`. These **readable references are identifiers**, not layers required for recovery, and their definitions are versioned.

All original numeric prices, starting bankroll, model equity before/after, implicit cash equity, feedback counts, modeled change fees, exact Q-value state digest, and original decision identifiers remain in the source event. The compact stream replaces the four repeated textual attributes with the eight-character reference plus a dictionary. Both streams include event receipts and provenance and must fully decode back into the same original events.

## Generated persistent evidence

- `trade_events.sqlite`: SQLite append-only synthetic Q decisions with compressed canonical payloads and per-event hash chain.
- `trade_events_full.jsonl.gz`: source-readable, recoverable event log preserving every original observation and all 46,080 receipts.
- `trade_events_symbolic.jsonl.gz`: symbolic references + full dictionary and numeric evidence; round-trip checked against the original JSONL.
- `track_results.jsonl.gz`: every path's forward result and Q state digest, including negative outcomes.
- `paper_decoder.txt`: reference table suitable for printing.
- `summary.json`: observed returns, costs, loss rates, relative cash/hold outcomes, and package storage comparison, with separate multi-asset controls.

## Verification

Cold database reopen re-executes AIscend's original `_apply_bar` using the stored source prices for every event, then compares each resulting policy action, Q digest and account value to the original. Hash-chained receipts and duplicate rejection are independently checked. The compressed symbolic archive must reconstruct the exact original JSONL bytes.

## What this cannot establish

Even a favorable synthetic forward result is not proof of profitable deployment. The generator is deterministic and may favor strategies; venue fees, liquidity, slippage, order constraints, adverse selection, regime breaks, taxes, and asset delistings are not modeled as exchange trades. The four independent single-asset paths do not represent BEAN choosing among the entire Coinbase catalog. For that test we need a separately preserved actual Coinbase market dataset, causal asset-ranking logic, fee-accurate trades, and forward frozen tests.

## Architecture reused

- [Bridge two-character ledger experiment](../two_character_ledger/README.md): reference codebook and original-value replay conventions.
- [Bridge PR #47](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/pull/47): existing distinct Bridge↔BEAN Q portfolio context adapter; not replaced or implicitly connected in this test.
- [AIscend src/bean_growth_adaptive.py](https://github.com/danieloculus0-bot/AIscend/blob/27e72a340e3a3437b3bee1c781c809941806a79d/src/bean_growth_adaptive.py): actual Q updates, pending action feedback, score persistence conventions.
- [AIscend scripts/bean_historical_replay.py](https://github.com/danieloculus0-bot/AIscend/blob/27e72a340e3a3437b3bee1c781c809941806a79d/scripts/bean_historical_replay.py): multi-asset control trading and cost rules.

BEAN Q learning belongs to AIscend's original strategy module. The Bridge experiment acts only as a durable transparent evidence recorder and decoder, without a second learning algorithm.
