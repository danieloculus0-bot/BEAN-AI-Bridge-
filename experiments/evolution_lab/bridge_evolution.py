"""BEAN AI Bridge Evolution Lab 001.

Synthetic novelty detection with the actual BEAN AttentionFilter as a logic gate.
Policies mutate; hidden truth, verification and fitness stay in the evaluator.
Purely offline with no physical, network, trade or ERP effects.

This is an operational self-monitoring benchmark, NOT a consciousness test.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from bean.cognition.attention import AttentionFilter


@dataclass(frozen=True)
class Policy:
    attention_threshold: float = 0.85
    confirmations: int = 3
    max_probes: int = 1
    ask_questions: bool = False


BASELINE = Policy()
RULE_COMPARATOR = Policy(attention_threshold=0.5, confirmations=2, max_probes=2, ask_questions=False)


class SimulatedAgent:
    """Observes only sensor reports; the oracle stays outside this object."""

    def __init__(self, policy: Policy, saved_state: dict | None = None):
        self.policy = policy
        self.belief = 0
        self.probes = 0
        self.false_probes = 0
        self.detected_at = None
        self.evidence = []
        if saved_state:
            self.belief = saved_state["belief"]
            self.probes = saved_state["probes"]
            self.false_probes = saved_state["false_probes"]
            self.detected_at = saved_state["detected_at"]
            self.evidence = list(saved_state["evidence"])
        self._streak = 0  # transitory attention state, intentionally cleared at restart

    def snapshot(self) -> dict:
        """Persist inspected facts, not unverified impressions."""
        return {"belief": self.belief, "probes": self.probes,
                "false_probes": self.false_probes, "detected_at": self.detected_at,
                "evidence": list(self.evidence)}

    def observe(self, step: int, a: int, b: int, verify) -> None:
        mismatch = (a != self.belief) + (b != self.belief)
        self._streak = self._streak + 1 if mismatch else 0
        if not mismatch:
            return
        event = {
            "id": step, "event_type": "observation",
            "severity": "warn" if mismatch == 2 else "info",
            "summary": "Novel state discrepancy from simulated sensors",
            "subtype": "simulated_state_discrepancy",
        }
        questions = ([{"question": "Investigate state discrepancy"}]
                     if self.policy.ask_questions else [])
        selected = AttentionFilter(threshold=self.policy.attention_threshold).build_window(
            [event], open_questions=questions
        ).event_ids()
        if not selected or self._streak < self.policy.confirmations:
            return
        if self.probes >= self.policy.max_probes:
            return
        self.probes += 1
        confirmed_state = int(verify())  # bounded simulated inspection tool
        self.evidence.append({"step": step, "observed_a": a, "observed_b": b,
                              "verified_state": confirmed_state})
        if confirmed_state == self.belief:
            self.false_probes += 1
        else:
            self.belief = confirmed_state
            if self.detected_at is None:
                self.detected_at = step
        self._streak = 0


def generate_case(seed: int) -> dict:
    """The evaluator owns ground truth. Only sensor pairs reach the agent."""
    rng = random.Random(seed)
    changed = rng.random() < 0.72
    change_at = rng.choice([3, 4, 5, 7]) if changed else None
    timeline = []
    for step in range(12):
        truth = int(changed and step >= change_at)
        a = truth ^ int(rng.random() < 0.20)
        b = truth ^ int(rng.random() < 0.28)
        timeline.append((a, b, truth))
    return {"changed": changed, "change_at": change_at, "timeline": timeline}


def evaluate(policy: Policy, seeds: list[int]) -> dict:
    points = 0.0
    hits = false_probes = probes = delays = changed_count = 0
    persisted = 0
    for seed in seeds:
        case = generate_case(seed)
        agent = SimulatedAgent(policy)
        for step, (a, b, truth) in enumerate(case["timeline"]):
            # The agent cannot read 'truth'; it can request one bounded verification.
            agent.observe(step, a, b, verify=lambda value=truth: value)
            if step == 6:
                snapshot = agent.snapshot()
                agent = SimulatedAgent(policy, saved_state=snapshot)
                persisted += int(agent.snapshot() == snapshot)
        detected = bool(case["changed"] and agent.belief == 1 and agent.detected_at is not None)
        if case["changed"]:
            changed_count += 1
            if detected:
                hits += 1
                delay = max(0, agent.detected_at - case["change_at"])
                delays += delay
                points += 4.0 - 0.2 * delay
            else:
                points -= 2.0
        else:
            points += 3.0 if agent.belief == 0 else -3.0
        points -= 0.17 * agent.probes + 0.45 * agent.false_probes
        probes += agent.probes
        false_probes += agent.false_probes
    n = max(1, len(seeds))
    return {"mean_score": round(points / n, 4),
            "change_recall": round(hits / changed_count, 4) if changed_count else None,
            "mean_probes": round(probes / n, 4),
            "mean_false_probes": round(false_probes / n, 4),
            "mean_detection_delay": round(delays / hits, 4) if hits else None,
            "restart_state_retained": persisted,
            "episodes": len(seeds), "changes": changed_count}


def mutate(policy: Policy, rng: random.Random) -> Policy:
    values = asdict(policy)
    field = rng.choice(list(values))
    if field == "attention_threshold":
        values[field] = rng.choice([0.30, 0.35, 0.45, 0.50, 0.60, 0.65, 0.75, 0.85])
    elif field == "confirmations":
        values[field] = rng.choice([1, 2, 3, 4])
    elif field == "max_probes":
        values[field] = rng.choice([1, 2, 3, 4])
    else:
        values[field] = not values[field]
    return Policy(**values)


def evolve(*, seed: int = 1337, generations: int = 6, population: int = 20) -> dict:
    """Use training outcomes for selection; untouched holdouts for final reporting."""
    if generations < 1 or population < 2:
        raise ValueError("generations must be >=1 and population must be >=2")
    rng = random.Random(seed)
    train = list(range(500, 560))
    holdout = list(range(12000, 12080))
    parents = [BASELINE, RULE_COMPARATOR]
    history = []
    for generation in range(generations):
        candidates = {BASELINE, RULE_COMPARATOR, *parents}
        while len(candidates) < population:
            candidates.add(mutate(rng.choice(parents), rng))
        scored = sorted(
            [(evaluate(p, train)["mean_score"], p) for p in candidates],
            key=lambda pair: (pair[0], -pair[1].confirmations, -pair[1].max_probes,
                              -pair[1].attention_threshold, pair[1].ask_questions),
            reverse=True,
        )
        parents = [policy for _, policy in scored[:min(5, len(scored))]]
        history.append({"generation": generation, "best_training_score": scored[0][0],
                        "best_policy": asdict(scored[0][1]), "candidates": len(candidates)})
    winner = parents[0]
    return {
        "label": "SYNTHETIC_AWARENESS_PROXY_NOT_CONSCIOUSNESS",
        "engine": "BEAN AttentionFilter, from real BEAN core",
        "random_seed": seed, "generations": generations,
        "training_episodes": len(train), "heldout_episodes": len(holdout),
        "training_seed_window": [min(train), max(train)],
        "heldout_seed_window": [min(holdout), max(holdout)],
        "history": history,
        "baseline": {"policy": asdict(BASELINE), "holdout": evaluate(BASELINE, holdout)},
        "rule_comparator": {"policy": asdict(RULE_COMPARATOR), "holdout": evaluate(RULE_COMPARATOR, holdout)},
        "evolved": {"policy": asdict(winner), "training": evaluate(winner, train),
                    "holdout": evaluate(winner, holdout)},
        "limitations": [
            "The agent is a finite-state controller using BEAN attention, not an LLM.",
            "Training and evaluation are synthetic with simulator-provided verification.",
            "General intelligence, subjective experience and unscripted curiosity are not established.",
            "Candidate mutations are bounded parameters, not arbitrary executable code.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--population", type=int, default=20)
    args = parser.parse_args()
    report = evolve(generations=args.generations, population=args.population)
    body = json.dumps(report, indent=2, sort_keys=True)
    print(body)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(body + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
