"""BEAN Bridge Lab010: actually execute and adopt synthetic growth strategies.

An online contextual bandit updates action values from realized mock portfolio
rewards. No exchange access, crypto credentials, live execution, or future leak.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

STRATEGIES = ("momentum", "reversion", "trend_3", "buy_hold", "cash")
FEE = 0.0007
START = 100.0


def make_world(seed: int, *, periods: int = 320) -> list[float]:
    """Hidden shifting regimes, reproducible without exposing their labels."""
    rng = random.Random(seed)
    regimes = ("momentum", "reversion", "bull", "bear", "noise")
    values = []
    previous = 0.0
    for t in range(periods):
        mode = regimes[(t // 64 + seed % 5) % len(regimes)]
        noise = rng.gauss(0, 0.007)
        if mode == "momentum":
            value = .78 * previous + noise
        elif mode == "reversion":
            value = -.78 * previous + noise
        elif mode == "bull":
            value = .0027 + .25 * previous + noise
        elif mode == "bear":
            value = -.0027 + .25 * previous + noise
        else:
            value = noise
        previous = max(-.075, min(.075, value))
        values.append(previous)
    return values


def context(history: list[float]) -> str:
    """Build a contextual feature exclusively from earlier observations."""
    if len(history) < 12:
        return "insufficient"
    tail = history[-11:]
    same = sum(a * b > 0 for a, b in zip(tail[:-1], tail[1:]))
    regime = "persistent" if same >= 7 else "alternating" if same <= 3 else "mixed"
    return regime + ("/up" if history[-1] > 0 else "/down")


def exposure(strategy: str, history: list[float]) -> int:
    """Execute a selected strategy as a long-or-cash market position."""
    if strategy == "cash":
        return 0
    if strategy == "buy_hold":
        return 1
    if not history:
        return 0
    if strategy == "momentum":
        return int(history[-1] > 0)
    if strategy == "reversion":
        return int(history[-1] < 0)
    if strategy == "trend_3":
        return int(sum(history[-3:]) > 0)
    raise ValueError("Unknown strategy")


@dataclass
class OnlinePolicy:
    """Reward-updated policy. No winning strategy hardcoded by regime."""
    q: dict[str, dict[str, float]] = field(default_factory=dict)
    visits: dict[str, dict[str, int]] = field(default_factory=dict)
    alpha: float = .08
    epsilon: float = .12

    def choose(self, state: str, rng: random.Random, *, explore: bool) -> str:
        if explore and rng.random() < self.epsilon:
            return rng.choice(STRATEGIES)
        scores = self.q.get(state, {})
        return max(STRATEGIES,
                   key=lambda a: (scores.get(a, 0.0), -STRATEGIES.index(a)))

    def learn(self, state: str, action: str, realized_bps: float) -> None:
        if action not in STRATEGIES or not math.isfinite(realized_bps):
            raise ValueError("invalid action or reward")
        old = self.q.setdefault(state, {}).get(action, 0.0)
        self.q[state][action] = old + self.alpha * (realized_bps - old)
        counts = self.visits.setdefault(state, {})
        counts[action] = counts.get(action, 0) + 1

    def save(self, path: Path) -> str:
        obj = {"schema": "bean.bridge.growth.v1", "q": self.q,
               "visits": self.visits, "alpha": self.alpha, "epsilon": self.epsilon,
               "source": "synthetic_mock_rewards_only"}
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def load(cls, path: Path) -> "OnlinePolicy":
        obj = json.loads(path.read_text())
        if obj.get("schema") != "bean.bridge.growth.v1":
            raise ValueError("unknown policy schema")
        if any(not isinstance(k, str) or
               any(a not in STRATEGIES or not math.isfinite(v)
                   for a, v in actions.items())
               for k, actions in obj["q"].items()):
            raise ValueError("invalid policy scores")
        return cls(q=obj["q"], visits=obj["visits"],
                   alpha=float(obj["alpha"]), epsilon=float(obj["epsilon"]))


def run_episode(returns: list[float], policy: OnlinePolicy | None = None,
                *, fixed: str | None = None, train: bool = False,
                seed: int = 0, record: bool = False) -> dict:
    """Every step executes a decision before seeing that step's price return."""
    if (policy is None) == (fixed is None):
        raise ValueError("Supply either policy or a fixed strategy")
    if fixed is not None and fixed not in STRATEGIES:
        raise ValueError("unknown fixed strategy")
    equity, held, peak, max_dd = START, 0, START, 0.0
    history: list[float] = []
    previous_strategy = None
    trades, switches = 0, 0
    counts = {s: 0 for s in STRATEGIES}
    log = []
    rng = random.Random(seed)
    for step, change in enumerate(returns):
        state = context(history)
        action = fixed if fixed is not None else policy.choose(
            state, rng, explore=train)
        target = exposure(action, history)
        fee = FEE if held != target else 0.0
        realized = target * change - fee
        equity *= 1 + realized
        if equity <= 0:
            raise AssertionError("insolvent mock ledger")
        if fee:
            trades += 1
        if previous_strategy is not None and action != previous_strategy:
            switches += 1
        held = target
        previous_strategy = action
        counts[action] += 1
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
        if train:
            # Only reward for actual selected-and-executed strategy is observed.
            policy.learn(state, action, realized * 10000)
        if record:
            log.append({"step": step, "context": state,
                        "strategy_executed": action, "exposure": target,
                        "realized_return": round(realized, 8),
                        "equity": round(equity, 8), "traded": bool(fee)})
        history.append(change)
    result = {"final": round(equity, 6),
              "net_return": round(equity / START - 1, 6),
              "max_drawdown": round(max_dd, 6), "trades": trades,
              "strategy_switches": switches, "strategy_use": counts}
    if record:
        result["action_ledger"] = log
    return result


def train_policy(*, episodes: int = 300, period: int = 320,
                 train_start: int = 10000) -> OnlinePolicy:
    policy = OnlinePolicy()
    for n in range(episodes):
        run_episode(make_world(train_start + n, periods=period),
                    policy, train=True, seed=900000 + n)
    return policy


def bootstrap_ci(differences: list[float], *,
                 repeats: int = 1600, seed: int = 19) -> list[float]:
    rng = random.Random(seed)
    spread = sorted(mean(rng.choices(differences, k=len(differences)))
                    for _ in range(repeats))
    return [round(spread[int(.025 * repeats)], 6),
            round(spread[int(.975 * repeats)], 6)]


def benchmark(*, episodes: int = 300, holdouts: int = 100,
              period: int = 320, train_start: int = 10000,
              test_start: int = 800000, out: Path | None = None) -> dict:
    if episodes < 1 or holdouts < 2 or period < 64:
        raise ValueError("insufficient trial settings")
    if not (train_start + episodes <= test_start or
            test_start + holdouts <= train_start):
        raise ValueError("training and holdout seeds overlap")
    learned = train_policy(episodes=episodes, period=period,
                           train_start=train_start)
    if out is None:
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            return grade(learned, holdouts, period, test_start,
                         Path(folder), save_report=False)
    out.mkdir(parents=True, exist_ok=True)
    return grade(learned, holdouts, period, test_start,
                 out, save_report=True)


def grade(learned, holdouts, period, test_start, out, *, save_report):
    path = out / "adopted_policy.json"
    digest = learned.save(path)
    deployed = OnlinePolicy.load(path)  # actual checkpoint adoption
    outcomes = {s: [] for s in ("adaptive", "untrained", *STRATEGIES)}
    ledger = []
    virgin = OnlinePolicy()
    for n in range(holdouts):
        world = make_world(test_start + n, periods=period)
        live = run_episode(world, deployed, seed=n, record=n < 2)
        if n < 2:
            ledger.append({"seed": test_start + n, "result": live})
        outcomes["adaptive"].append(live["net_return"])
        outcomes["untrained"].append(
            run_episode(world, virgin, seed=n)["net_return"])
        for strategy in STRATEGIES:
            outcomes[strategy].append(
                run_episode(world, fixed=strategy)["net_return"])
    averages = {k: round(mean(v), 6) for k, v in outcomes.items()}
    # Strong comparison: best fixed strategy chosen in hindsight on holdout.
    # It is a descriptive bound, not used to train or select the policy.
    fixed_best = max(STRATEGIES, key=lambda s: averages[s])
    differences = [a - b for a, b in zip(outcomes["adaptive"],
                                          outcomes[fixed_best])]
    improvement = [a - b for a, b in zip(outcomes["adaptive"],
                                          outcomes["untrained"])]
    interval = bootstrap_ci(differences)
    report = {
        "schema": "bean.bridge.growth.benchmark.v1",
        "environment": "SYNTHETIC_ONLY",
        "train_episodes": sum(sum(v.values()) for v in deployed.visits.values()) // period,
        "holdout_episodes": holdouts, "periods_per_episode": period,
        "test_seeds": [test_start, test_start + holdouts - 1],
        "checkpoint_sha256": digest, "checkpoint_reloaded": True,
        "average_net_returns": averages,
        "strongest_fixed_on_holdout": fixed_best,
        "mean_uplift_vs_strongest_fixed": round(mean(differences), 6),
        "paired_bootstrap_95pct_ci": interval,
        "mean_uplift_vs_untrained": round(mean(improvement), 6),
        "untrained_bootstrap_95pct_ci": bootstrap_ci(improvement, seed=31),
        "passed_synthetic_gate": interval[0] > 0 and
                                 bootstrap_ci(improvement, seed=31)[0] > 0,
        "examples": ledger,
        "limits": "Synthetic return processes are easy and unrealistic; "
                  "not proof of live crypto trading advantage."
    }
    if save_report:
        (out / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description="BEAN executed synthetic growth learning")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--train", type=int, default=300)
    p.add_argument("--holdouts", type=int, default=100)
    args = p.parse_args()
    report = benchmark(episodes=args.train, holdouts=args.holdouts,
                       out=args.out)
    print(json.dumps({k: v for k, v in report.items()
                      if k != "examples"}, indent=2))


if __name__ == "__main__":
    main()
