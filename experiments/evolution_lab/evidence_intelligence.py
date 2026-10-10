"""BEAN Evidence Intelligence Lab 003.

Real BEAN AttentionFilter gates bounded investigations. This experimental
controller models sensor reliability from verifier-provided feedback, records
competing explanations, and survives interrupted sessions. Evaluator-owned
truth NEVER enters observe() except through the explicitly metered verifier.

Synthetic simulation only. No LLM, cognition or consciousness claim.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from bean.cognition.attention import AttentionFilter

from experiments.evolution_lab.bridge_evolution import RULE_COMPARATOR, SimulatedAgent, generate_case


PROFILES = ("standard", "correlated_noise", "delayed_sensors", "drifting_a", "stuck_b", "late_shift", "early_shift")
TRAIN_PROFILES = ("standard", "correlated_noise", "delayed_sensors")
ADVERSARIAL_PROFILES = ("drifting_a", "stuck_b", "late_shift", "early_shift")


@dataclass(frozen=True)
class EvidencePolicy:
    attention_threshold: float = 0.45
    probe_confidence: float = 0.58
    max_probes: int = 3
    min_persistence: int = 1
    reliability_decay: float = 0.95
    independent_check_period: int = 0
    learn_sensor_reliability: bool = True


class EvidenceAgent:
    """Bounded belief, error model, unresolved hypotheses, and audit state."""

    def __init__(self, policy: EvidencePolicy, state: dict | None = None):
        self.policy = policy
        self.belief = 0
        self.probes = 0
        self.false_probes = 0
        self.detected_at = None
        self.reliability = {"A": [2.0, 1.0], "B": [2.0, 1.0]}
        self.evidence: list[dict] = []
        self.hypotheses: dict[str, dict] = {}
        self._streak = 0
        self._next_id = 1
        self.forecasts: list[dict] = []
        if state is not None:
            self.belief = int(state["belief"])
            self.probes = int(state["probes"])
            self.false_probes = int(state["false_probes"])
            self.detected_at = state["detected_at"]
            self.reliability = {name: list(state["reliability"][name]) for name in ("A", "B")}
            self.evidence = list(state["evidence"])
            self.hypotheses = {k: dict(v) for k, v in state["hypotheses"].items()}
            self._streak = int(state["_streak"])
            self._next_id = int(state["_next_id"])
            self.forecasts = list(state["forecasts"])

    def snapshot(self) -> dict:
        """Only inspected facts and beliefs, never evaluator truth."""
        return {
            "belief": self.belief, "probes": self.probes,
            "false_probes": self.false_probes, "detected_at": self.detected_at,
            "reliability": {k: list(v) for k, v in self.reliability.items()},
            "evidence": list(self.evidence),
            "hypotheses": {k: dict(v) for k, v in self.hypotheses.items()},
            "_streak": self._streak, "_next_id": self._next_id,
            "forecasts": list(self.forecasts),
        }

    def source_accuracy(self, name: str) -> float:
        if not self.policy.learn_sensor_reliability:
            return 2.0 / 3.0
        good, bad = self.reliability[name]
        return max(0.06, min(0.94, good / (good + bad)))

    def forecast(self, readings: dict[str, int]) -> float:
        """Log-odds fusion with a conservative continuity prior."""
        odds = math.log(0.6 / 0.4) * (1 if self.belief else -1)
        for name in ("A", "B"):
            value = readings.get(name)
            if value is None:
                continue
            p = self.source_accuracy(name)
            odds += (2 * value - 1) * math.log(p / (1 - p))
        return 1 / (1 + math.exp(-max(-14, min(14, odds))))

    def _hypothesis(self, key: str, explanation: str, step: int, evidence: str, falsification: str):
        old = self.hypotheses.get(key)
        if old:
            old["evidence_refs"].append(evidence)
            old["last_step"] = step
        else:
            self.hypotheses[key] = {
                "id": f"H{self._next_id}", "statement": explanation,
                "status": "unresolved", "evidence_refs": [evidence],
                "first_step": step, "last_step": step,
                "what_would_falsify": falsification,
            }
            self._next_id += 1

    def _calibrate(self, readings: dict[str, int], truth: int, step: int):
        decay = self.policy.reliability_decay
        for source in ("A", "B"):
            value = readings.get(source)
            if value is None:
                continue
            good, bad = self.reliability[source]
            matched = int(value == truth)
            self.reliability[source] = [
                good * decay + matched, bad * decay + (1 - matched)
            ]
            if not matched:
                self._hypothesis(
                    f"source_{source}_unreliable",
                    f"Source {source} may be unreliable",
                    step, f"verify:{step}:{source}",
                    f"Three later independent verified observations of source {source} agree",
                )
        if readings.get("A") is not None and readings.get("A") == readings.get("B") and readings["A"] != truth:
            self._hypothesis(
                "shared_fault",
                "Both sensors may share a failure mode or common bias",
                step, f"verify:{step}:both",
                "Later independent checks establish both sensors are correct under matching conditions",
            )

    def observe(self, step: int, readings: dict[str, int], verify) -> dict:
        """choose a test; verification is never called without a metered decision."""
        if any(k not in {"A", "B"} for k in readings):
            raise ValueError("unknown source")
        if any(v not in (0, 1, None) for v in readings.values()):
            raise ValueError("invalid sensor value")

        estimate = self.forecast(readings)
        self.forecasts.append({"step": step, "p_state_1": round(estimate, 6),
                               "readings": dict(readings)})
        observed = [v for v in readings.values() if v is not None]
        disagreement = (len(set(observed)) > 1)
        opposing = any(v != self.belief for v in observed)
        suspicious = bool(disagreement or opposing)
        self._streak = self._streak + 1 if suspicious else 0
        guess = int(estimate >= 0.5)
        candidate_change = guess != self.belief
        confidence = estimate if candidate_change and guess else (1 - estimate if candidate_change else max(estimate, 1 - estimate))
        due_check = self.policy.independent_check_period > 0 and step > 0 and step % self.policy.independent_check_period == 0

        should_probe = False
        why = None
        if self.probes < self.policy.max_probes:
            if due_check:
                should_probe, why = True, "independent_calibration"
            elif suspicious and self._streak >= self.policy.min_persistence:
                event = {
                    "id": step, "event_type": "observation",
                    "severity": "warn",
                    "summary": "Unresolved sensor discrepancy requiring evidence check",
                    "subtype": "evidence_conflict",
                }
                attention = AttentionFilter(threshold=self.policy.attention_threshold).build_window(
                    [event],
                    # An unexplained discrepancy can itself open an investigation.
                    # Do not require a previously verified hypothesis to act.
                    open_questions=[{"question": "Investigate sensor discrepancy"}],
                )
                if attention.event_ids() and (
                    candidate_change and confidence >= self.policy.probe_confidence or disagreement
                ):
                    should_probe, why = True, "uncertain_change" if candidate_change else "source_disagreement"

        if not should_probe:
            return {"step": step, "action": "observe", "estimate": round(estimate, 6),
                    "belief": self.belief, "open_hypotheses": len(self.hypotheses)}

        truth = int(verify())
        if truth not in (0, 1):
            raise ValueError("invalid verification")
        prior = self.belief
        self.probes += 1
        if truth == prior:
            self.false_probes += 1
        else:
            self.belief = truth
            if self.detected_at is None:
                self.detected_at = step
        self._calibrate(readings, truth, step)
        record = {"step": step, "reason": why, "prior_belief": prior,
                  "verified_state": truth, "readings": dict(readings),
                  "estimate_before_verification": round(estimate, 6)}
        self.evidence.append(record)
        self._streak = 0
        return {"step": step, "action": "verify", "reason": why,
                "estimate": round(estimate, 6), "belief": self.belief,
                "open_hypotheses": len(self.hypotheses)}


def case_for(seed: int, profile: str) -> dict:
    if profile in ("standard", "correlated_noise", "delayed_sensors"):
        return generate_case(seed, profile)
    if profile not in ADVERSARIAL_PROFILES:
        raise ValueError("unknown sensor profile")
    # Reuse identical ground truth to make fixed-policy comparisons fair.
    case = generate_case(seed)
    timeline = []
    altered_change_at = case["change_at"]
    if case["changed"] and profile == "late_shift":
        altered_change_at = [8, 9, 10][seed % 3]
    if case["changed"] and profile == "early_shift":
        altered_change_at = [1, 2][seed % 2]
    for step, (a, b, truth) in enumerate(case["timeline"]):
        if profile in ("late_shift", "early_shift"):
            new_truth = int(case["changed"] and step >= altered_change_at)
            a, b, truth = a ^ truth ^ new_truth, b ^ truth ^ new_truth, new_truth
        if profile == "drifting_a" and step >= 4:
            a = 1 - truth  # channel A becomes systematically inverted
        if profile == "stuck_b" and step >= 4:
            b = 0  # channel B becomes stuck low
        timeline.append((a, b, truth))
    return {**case, "change_at": altered_change_at, "timeline": timeline}


def evaluate_previous(seeds: list[int], profile: str) -> dict:
    """The exact Lab 002 controller on the same new ground-truth traces."""
    score = 0.0
    hits = changes = false_probes = probes = delay = saved = 0
    for seed in seeds:
        case = case_for(seed, profile)
        agent = SimulatedAgent(RULE_COMPARATOR)
        for step, (a, b, truth) in enumerate(case["timeline"]):
            agent.observe(step, a, b, verify=lambda x=truth: x)
            if step == 6:
                snapshot = agent.snapshot()
                agent = SimulatedAgent(RULE_COMPARATOR, saved_state=snapshot)
                saved += int(agent.snapshot() == snapshot)
        success = case["changed"] and agent.belief == 1 and agent.detected_at is not None
        if case["changed"]:
            changes += 1
            if success:
                hits += 1
                lag = max(0, agent.detected_at - case["change_at"])
                delay += lag
                score += 4.0 - 0.2 * lag
            else:
                score -= 2.0
        else:
            score += 3.0 if agent.belief == 0 else -3.0
        score -= 0.17 * agent.probes + 0.45 * agent.false_probes
        probes += agent.probes
        false_probes += agent.false_probes
    n = len(seeds)
    return {"episodes": n, "actual_changes": changes,
            "change_recall": round(hits / changes, 4) if changes else None,
            "mean_score": round(score / n, 4),
            "mean_probes": round(probes / n, 4),
            "mean_false_probes": round(false_probes / n, 4),
            "mean_delay": round(delay / hits, 4) if hits else None,
            "restart_state_retained": saved}


def evaluate_evidence(policy: EvidencePolicy, seeds: list[int], profile: str) -> dict:
    points = 0.0
    probes = false_probes = changed = detected = delay = retained = hypothesis_count = 0
    squared_error = forecast_count = bad_certainty = 0
    for seed in seeds:
        case = case_for(seed, profile)
        agent = EvidenceAgent(policy)
        for step, (a, b, truth) in enumerate(case["timeline"]):
            # Only this evaluator owns actual truth and may construct the verifier.
            agent.observe(step, {"A": a, "B": b}, verify=lambda x=truth: x)
            predicted = agent.forecasts[-1]["p_state_1"]
            squared_error += (predicted - truth) ** 2
            bad_certainty += int((predicted > 0.8 and truth == 0) or
                                 (predicted < 0.2 and truth == 1))
            forecast_count += 1
            if step == 6:
                snap = json.loads(json.dumps(agent.snapshot()))
                agent = EvidenceAgent(policy, snap)
                retained += int(agent.snapshot() == snap)
        success = bool(case["changed"] and agent.belief == 1 and agent.detected_at is not None)
        if case["changed"]:
            changed += 1
            if success:
                detected += 1
                lag = max(0, agent.detected_at - case["change_at"])
                delay += lag
                points += 4.0 - 0.2 * lag
            else:
                points -= 2.0
        else:
            points += 3.0 if agent.belief == 0 else -3.0
        points -= 0.17 * agent.probes + 0.45 * agent.false_probes
        probes += agent.probes
        false_probes += agent.false_probes
        hypothesis_count += len(agent.hypotheses)
    n = len(seeds)
    return {
        "episodes": n, "actual_changes": changed,
        "change_recall": round(detected / changed, 4) if changed else None,
        "mean_score": round(points / n, 4),
        "mean_probes": round(probes / n, 4),
        "mean_false_probes": round(false_probes / n, 4),
        "mean_delay": round(delay / detected, 4) if detected else None,
        "brier": round(squared_error / forecast_count, 4) if forecast_count else None,
        "high_confidence_errors": bad_certainty,
        "mean_hypotheses": round(hypothesis_count / n, 4),
        "restart_state_retained": retained,
    }


def train_policy(seed: int = 501, population: int = 16) -> tuple[EvidencePolicy, list[dict]]:
    """Search typed parameters using only disjoint training episodes."""
    if not 2 <= population <= 64:
        raise ValueError("population outside search bounds")
    rng = random.Random(seed)
    default = EvidencePolicy()
    candidates = {default}
    while len(candidates) < population:
        candidates.add(EvidencePolicy(
            attention_threshold=rng.choice([0.35, 0.45, 0.55]),
            probe_confidence=rng.choice([0.53, 0.60, 0.70, 0.78]),
            max_probes=rng.choice([2, 3, 4]),
            min_persistence=rng.choice([1, 2, 3]),
            reliability_decay=rng.choice([0.70, 0.9, 0.98]),
            independent_check_period=rng.choice([0, 4, 6]),
        ))
    train = list(range(2100, 2135))
    results = []
    for p in sorted(candidates, key=lambda x: tuple(asdict(x).values())):
        metrics = [evaluate_evidence(p, train, name) for name in TRAIN_PROFILES]
        fitness = round(sum(x["mean_score"] for x in metrics) / len(metrics), 4)
        # Optimize task success; precision and calibration still independently reported.
        results.append({"policy": asdict(p), "fitness": fitness})
    results.sort(key=lambda x: (-x["fitness"], tuple(x["policy"].values())))
    return EvidencePolicy(**results[0]["policy"]), results


def study() -> dict:
    selected, table = train_policy()
    holdout = list(range(16000, 16080))
    return {
        "label": "SYNTHETIC_EVIDENCE_RELIABILITY_EXPERIMENT_NOT_AGI",
        "selected_policy": asdict(selected),
        "training_window": [2100, 2134],
        "evaluation_window": [min(holdout), max(holdout)],
        "training_top_five": table[:5],
        "results": {
            profile: {
                "fixed_002": evaluate_previous(holdout, profile),
                "evidence_003": evaluate_evidence(selected, holdout, profile),
                "default_003": evaluate_evidence(EvidencePolicy(), holdout, profile),
                "no_sensor_learning": evaluate_evidence(
                    replace(selected, learn_sensor_reliability=False), holdout, profile
                ),
                "no_scheduled_verification": evaluate_evidence(
                    replace(selected, independent_check_period=0), holdout, profile
                ),
            }
            for profile in PROFILES
        },
        "limits": [
            "Verifier is a simulated oracle under bounded explicit investigation.",
            "The evaluator, not the agent, holds all ground-truth values.",
            "Reliability statistics come only from inspected outcomes.",
            "No live sensory feedback, consciousness, AGI or autonomous code writing is established.",
            "The adaptive agent uses real BEAN AttentionFilter, but its reliability controller is new research code.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="BEAN evidence intelligence, synthetic replay")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = json.dumps(study(), indent=2, sort_keys=True)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
