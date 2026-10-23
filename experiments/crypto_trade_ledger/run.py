"""Replay AIscend's actual BEAN Q learner with a compressed, paper-decodable event ledger.

Synthetic market stress test only. Imports AIscend's real learner and historical
replay functions from an explicitly supplied checkout. No exchange or wallet use.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
import statistics
import sys
import zlib

SCHEMA = "bridge.crypto.twochar.v1"
BANKROLL = 1000.0
BAR_SECONDS = 300
BARS = 240
WARMUP = 160
SEEDS = range(12)
MARKETS = ("BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD")
REGIMES = ("uptrend", "downtrend", "sideways", "trend_reversal")
BASE_PRICE = {"BTC-USD": 62000.0, "ETH-USD": 2800.0,
              "SOL-USD": 140.0, "DOGE-USD": 0.22}
CODEBOOK = {
    "market": {"M1": "BTC-USD", "M2": "ETH-USD", "M3": "SOL-USD", "M4": "DOGE-USD"},
    "regime": {"R1": "uptrend", "R2": "downtrend", "R3": "sideways", "R4": "trend_reversal"},
    "action": {"A1": "momentum", "A2": "reversion", "A3": "trend_3",
               "A4": "buy_hold", "A5": "cash"},
    "exposure": {"P0": "CASH", "P1": "LONG"},
}
FIELDS = ("market", "regime", "action", "exposure")
REVERSE = {field: {v: k for k, v in mapping.items()}
           for field, mapping in CODEBOOK.items()}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(event):
    return "".join(REVERSE[field][event[field]] for field in FIELDS)


def decode(symbol):
    if len(symbol) != 8:
        raise ValueError("bad symbolic record")
    return {field: CODEBOOK[field][symbol[i * 2:i * 2 + 2]]
            for i, field in enumerate(FIELDS)}


def generated_bars(regime, seed, market):
    """Four predeclared price regimes; no market history or profitability claim."""
    nonce = int(sha(f"{regime}:{seed}:{market}".encode())[:16], 16)
    rng = random.Random(nonce)
    price = BASE_PRICE[market]
    path = []
    anchor = math.log(price)
    previous_return = 0.0
    # Synthetic 5-minute log-return scale and shock assumptions.
    vol = {"BTC-USD": .0020, "ETH-USD": .0026,
           "SOL-USD": .0032, "DOGE-USD": .0045}[market]
    for i in range(BARS):
        noise = rng.gauss(0, vol)
        if regime == "uptrend":
            change = .00043 + noise
        elif regime == "downtrend":
            change = -.00047 + noise
        elif regime == "sideways":
            # Explicit mean-reversion stress condition, not a generated free profit.
            change = -.37 * previous_return + noise
        else:
            change = (.00055 if i < BARS // 2 else -.00085) + noise
        if i % 53 == 17:
            change -= .012  # downside surprise retained, not filtered
        previous_return = change
        opening = price
        price = opening * math.exp(change)
        if not math.isfinite(price) or price <= 0:
            raise AssertionError("bad market fixture")
        path.append({"ts": 1767225600 + i * BAR_SECONDS,
                     "open": round(opening, 10), "close": round(price, 10)})
    return path


def fresh_state(create_state):
    state = create_state()
    state["equity"] = BANKROLL
    state["peak"] = BANKROLL
    return state


def one_step(apply_bar, state, *, regime, seed, market, step, bar):
    before = state["equity"]
    prior_held = int(state["held"])
    pending = state["pending"]
    prior_visits = sum(sum(x.values()) for x in state["visits"].values())
    changed = apply_bar(state, {"open": bar["open"], "close": bar["close"]},
                        bar["ts"], market)
    if not changed:
        raise AssertionError("missing or duplicate synthetic step")
    visits = sum(sum(x.values()) for x in state["visits"].values())
    if visits - prior_visits != (1 if pending is not None else 0):
        raise AssertionError("Q feedback mismatch")
    exposure = "LONG" if state["held"] else "CASH"
    out = {
        "schema": SCHEMA, "source_kind": "synthetic", "seed": seed,
        "regime": regime, "market": market, "step": step,
        "timestamp": bar["ts"], "open": bar["open"], "close": bar["close"],
        "starting_bankroll_usd": BANKROLL,
        "equity_before_usd": round(before, 8),
        "equity_after_usd": round(state["equity"], 8),
        "cash_after_usd": round(state["equity"] if not state["held"] else 0.0, 8),
        "action": state["last_action"], "exposure": exposure,
        "evaluated_previous_action": pending["action"] if pending else None,
        "modeled_fee_fraction": .0007 if pending and prior_held != int(state["held"]) else 0.0,
        "q_updates_cumulative": visits,
        "q_values_sha256": sha(canonical(state["q"])),
        "strategy_changes_cumulative": state["strategy_changes"],
        "behavior_revisions_cumulative": state["behavior_revisions"],
    }
    out["symbol"] = encode(out)
    assert decode(out["symbol"]) == {field: out[field] for field in FIELDS}
    return out


def baseline_hold(bars, fee):
    start, end = bars[WARMUP]["open"], bars[-1]["close"]
    return (1 - fee) ** 2 * end / start - 1


def drawdown(path):
    peak = path[0]
    biggest = 0.0
    for v in path:
        peak = max(peak, v)
        biggest = max(biggest, 1 - v / peak)
    return biggest


def create_store(path):
    db = sqlite3.connect(str(path))
    db.execute("""CREATE TABLE events (
        seq INTEGER PRIMARY KEY, run_id TEXT NOT NULL, step INTEGER NOT NULL,
        compressed BLOB NOT NULL, payload_sha TEXT NOT NULL,
        previous_hash TEXT NOT NULL, chain_hash TEXT NOT NULL,
        UNIQUE(run_id,step))""")
    db.execute("CREATE INDEX idx_run_step ON events(run_id,step)")
    return db


def verify_store(path, expected, apply_bar, create_state):
    db = sqlite3.connect(str(path))
    old = "GENESIS"
    state = None
    last_id = None
    total = 0
    for seq, run_id, step, packed, fingerprint, previous, chain in db.execute(
            "SELECT seq,run_id,step,compressed,payload_sha,previous_hash,chain_hash "
            "FROM events ORDER BY seq"):
        obj = json.loads(zlib.decompress(packed))
        assert sha(canonical(obj)) == fingerprint
        assert previous == old
        assert chain == sha(canonical([previous, fingerprint]))
        assert seq == total + 1
        assert int(step) == int(obj["step"])
        assert run_id == f"{obj['regime']}:{obj['seed']}:{obj['market']}"
        assert decode(obj["symbol"]) == {key: obj[key] for key in FIELDS}
        if run_id != last_id:
            assert step == 0
            last_id = run_id
            state = fresh_state(create_state)
        rebuilt = one_step(apply_bar, state, regime=obj["regime"],
                           seed=obj["seed"], market=obj["market"],
                           step=step, bar={"ts": obj["timestamp"],
                                           "open": obj["open"],
                                           "close": obj["close"]})
        assert rebuilt == obj, f"cold replay divergence at {seq}"
        total += 1
        old = chain
    assert total == expected
    try:
        db.execute("INSERT INTO events(seq,run_id,step) VALUES (1,'duplicate',0)")
    except sqlite3.IntegrityError:
        duplicate_rejected = True
    else:
        duplicate_rejected = False
    assert duplicate_rejected
    assert old != sha(canonical(["0" * 64, "0" * 64]))
    db.close()
    return {"events": total, "chain_tip": old, "restarted_original_replay": True,
            "duplicate_rejected": duplicate_rejected}


def compact_line(record):
    row = json.loads(json.dumps(record))
    evt = row["event"]
    symbols = evt.pop("symbol")
    for field in FIELDS:
        del evt[field]
    evt["refs"] = symbols
    return canonical(row) + b"\n"


def expand_compact(record):
    obj = json.loads(canonical(record))
    evt = obj["event"]
    symbol = evt.pop("refs")
    evt["symbol"] = symbol
    evt.update(decode(symbol))
    return obj


def aggregate(rows):
    if not rows:
        return None
    return {
        "tracks": len(rows),
        "bean_mean_forward_pct": round(100 * statistics.mean(r["bean_return"] for r in rows), 4),
        "bean_median_forward_pct": round(100 * statistics.median(r["bean_return"] for r in rows), 4),
        "hold_mean_forward_pct": round(100 * statistics.mean(r["hold_return"] for r in rows), 4),
        "beat_cash": sum(r["bean_return"] > 0 for r in rows),
        "beat_hold": sum(r["bean_return"] > r["hold_return"] for r in rows),
        "losing_tracks": sum(r["bean_return"] < 0 for r in rows),
        "worst_forward_pct": round(100 * min(r["bean_return"] for r in rows), 4),
        "best_forward_pct": round(100 * max(r["bean_return"] for r in rows), 4),
        "mean_forward_max_drawdown_pct": round(100 * statistics.mean(r["max_drawdown"] for r in rows), 4),
        "mean_forward_q_updates": round(statistics.mean(r["forward_q_updates"] for r in rows), 2),
        "mean_forward_position_changes": round(statistics.mean(r["forward_position_changes"] for r in rows), 2),
        "mean_modeled_transaction_cost_pct": round(statistics.mean(r["forward_position_changes"] for r in rows) * .0007 * 100, 4),
    }


def execute(aiscend, out):
    sys.path.insert(0, str(Path(aiscend).resolve()))
    from src.bean_growth_adaptive import _fresh_state, BeanAdaptiveGrowthGate, MODEL_FEE
    from scripts.bean_historical_replay import run as market_run
    if abs(MODEL_FEE - .0007) > 1e-12:
        raise ValueError("AIscend learner fee changed; refresh research contract")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "trade_events.sqlite"
    if db_path.exists():
        db_path.unlink()
    db = create_store(db_path)
    prev = "GENESIS"
    seq = 0
    originals = []
    compact = []
    trial_rows = []
    multiasset_rows = []
    changed_counts = 0
    try:
        for regime in REGIMES:
            for seed in SEEDS:
                paths = {m: generated_bars(regime, seed, m) for m in MARKETS}
                # Separate four-asset, no-learning controls using AIscend's actual
                # existing historical engine (its 0.006 per side cost assumption).
                holdout_bars = [
                    {"ts": paths[MARKETS[0]][i]["ts"],
                     "prices": {m: {"open": paths[m][i]["open"],
                                    "close": paths[m][i]["close"]} for m in MARKETS}}
                    for i in range(WARMUP, BARS)
                ]
                for mode in ("cash", "buy_hold", "momentum", "persistent"):
                    result = market_run(holdout_bars, mode, 12, .005,
                                        starting=BANKROLL, pairs=MARKETS)
                    multiasset_rows.append({"regime": regime, "seed": seed,
                                            "strategy": mode, **result})
                for market in MARKETS:
                    state = fresh_state(_fresh_state)
                    start_mark = None
                    forward_path = []
                    count_at_cut = 0
                    revisions_at_cut = 0
                    trades_at_cut = 0
                    for i, bar in enumerate(paths[market]):
                        if i == WARMUP:
                            start_mark = state["equity"]
                            count_at_cut = sum(sum(v.values()) for v in state["visits"].values())
                            revisions_at_cut = state["behavior_revisions"]
                            trades_at_cut = state["mock_trades"]
                            state["bootstrapped"] = True
                        event = one_step(BeanAdaptiveGrowthGate._apply_bar, state,
                                         regime=regime, seed=seed, market=market,
                                         step=i, bar=bar)
                        if i >= WARMUP:
                            forward_path.append(state["equity"])
                        seq += 1
                        run_id = f"{regime}:{seed}:{market}"
                        payload = canonical(event)
                        fingerprint = sha(payload)
                        chain = sha(canonical([prev, fingerprint]))
                        db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                                   (seq, run_id, i, zlib.compress(payload, 6),
                                    fingerprint, prev, chain))
                        record = {"seq": seq, "run_id": run_id, "event": event,
                                  "payload_sha256": fingerprint, "previous_hash": prev,
                                  "chain_hash": chain}
                        originals.append(canonical(record) + b"\n")
                        compact.append(compact_line(record))
                        assert expand_compact(json.loads(compact[-1])) == record
                        prev = chain
                    assert start_mark is not None and start_mark > 0
                    before = state["equity"] / start_mark - 1
                    benchmark = baseline_hold(paths[market], MODEL_FEE)
                    forward_q = (sum(sum(v.values()) for v in state["visits"].values())
                                 - count_at_cut)
                    changes = state["behavior_revisions"] - revisions_at_cut
                    changed_counts += changes
                    trial_rows.append({
                        "regime": regime, "seed": seed, "market": market,
                        "bankroll_usd": BANKROLL, "starting_forward_equity_usd": round(start_mark, 6),
                        "ending_equity_usd": round(state["equity"], 6),
                        "bean_return": before, "hold_return": benchmark,
                        "max_drawdown": drawdown([start_mark, *forward_path]),
                        "forward_q_updates": forward_q,
                        "forward_policy_changes": changes,
                        "forward_position_changes": state["mock_trades"] - trades_at_cut,
                        "q_state_digest": sha(canonical(state["q"])),
                    })
                db.commit()
    finally:
        db.close()
    verified = verify_store(db_path, seq, BeanAdaptiveGrowthGate._apply_bar, _fresh_state)
    raw = b"".join(originals)
    head = canonical({"schema": SCHEMA, "kind": "compact",
                      "codebook": CODEBOOK, "events": seq}) + b"\n"
    dense = head + b"".join(compact)
    full_archive = gzip.compress(raw, compresslevel=9, mtime=0)
    dense_archive = gzip.compress(dense, compresslevel=9, mtime=0)
    (out / "trade_events_full.jsonl.gz").write_bytes(full_archive)
    (out / "trade_events_symbolic.jsonl.gz").write_bytes(dense_archive)
    (out / "track_results.jsonl.gz").write_bytes(
        gzip.compress(b"".join(canonical(row) + b"\n" for row in trial_rows),
                      compresslevel=9, mtime=0))
    recovered = gzip.decompress(dense_archive).splitlines()
    header = json.loads(recovered[0])
    assert header["codebook"] == CODEBOOK and header["events"] == seq
    decoded = b"".join(canonical(expand_compact(json.loads(line))) + b"\n"
                       for line in recovered[1:])
    assert decoded == raw
    assert gzip.decompress(full_archive) == raw
    paper = ["BEAN CRYPTO SYMBOL DECODER / VERSION 1", "",
             "Each event has eight readable characters:", "MMRRAAPP",
             "market (MM), regime (RR), Q action (AA), exposure (PP)", ""]
    for title, table in CODEBOOK.items():
        paper.append(title.upper())
        paper.extend(f"{key} = {value}" for key, value in table.items())
        paper.append("")
    (out / "paper_decoder.txt").write_text("\n".join(paper) + "\n", encoding="utf-8")
    result = {
        "schema": SCHEMA, "research_kind": "deterministic_synthetic_paper_trading",
        "real_exchange_fills": 0, "live_market_prices": False,
        "actual_policy": "AIscend.src.bean_growth_adaptive.BeanAdaptiveGrowthGate._apply_bar",
        "model_fee_per_position_change": MODEL_FEE,
        "starting_bankroll_per_independent_track_usd": BANKROLL,
        "assets": MARKETS, "regimes": REGIMES, "seeds_per_regime": len(SEEDS),
        "warmup_bars": WARMUP, "forward_bars": BARS - WARMUP,
        "separate_single_asset_tracks": len(trial_rows),
        "total_events": seq, "q_feedback_updates": seq - len(trial_rows),
        "forward_policy_revisions": changed_counts,
        "by_regime": {r: aggregate([x for x in trial_rows if x["regime"] == r])
                      for r in REGIMES},
        "all_tracks": aggregate(trial_rows),
        "multiasset_controls": {strategy: aggregate([
            {"bean_return": x["net_return"],
             "hold_return": 0.0, "max_drawdown": x["max_drawdown"],
             "forward_q_updates": 0, "forward_position_changes": x["trades"]} for x in multiasset_rows
            if x["strategy"] == strategy]) for strategy in
                                ("cash", "buy_hold", "momentum", "persistent")},
        "storage": {
            "full_jsonl_bytes": len(raw), "full_gzip_bytes": len(full_archive),
            "symbolic_plus_dictionary_jsonl_bytes": len(dense),
            "symbolic_gzip_bytes": len(dense_archive),
            "percent_gzip_saved": round(100 * (1 - len(dense_archive) /
                                               max(1, len(full_archive))), 3),
            "original_decompressed_sha256": sha(raw),
            "symbolic_decompressed_sha256": sha(dense),
            "symbol_codebook_sha256": sha(canonical(CODEBOOK)),
        },
        "ledger": verified,
        "research_limits": ("Synthetic regimes, Q learning continues causally "
                            "during forward evaluation; no frozen-policy holdout, "
                            "no Coinbase data, no shared multi-asset Q portfolio, "
                            "no claim of profitability or learning transfer."),
    }
    (out / "summary.json").write_bytes(json.dumps(result, indent=2,
                                                  sort_keys=True).encode() + b"\n")
    assert verified["events"] == len(SEEDS)*len(REGIMES)*len(MARKETS)*BARS
    assert seq == 46080
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aiscend", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    opts = ap.parse_args()
    execute(opts.aiscend, opts.out)
