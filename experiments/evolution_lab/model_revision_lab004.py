"""BEAN Lab 004: investigate when previously learned reliability stops working.

This is a synthetic extension of the actual BEAN AttentionFilter-driven Lab 003
controller. Verification can only occur after an explicit metered decision;
ground truth and evaluation rules remain outside the agent. We compare ordinary
persistent memory, error-triggered model revision, and independently scheduled
calibration checks. No LLMs, network access, robots, trades, or real sensors.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from experiments.evolution_lab.evidence_intelligence import EvidenceAgent, EvidencePolicy, case_for


@dataclass(frozen=True)
class RevisionRules:
    enabled: bool = True
    surprise_likelihood: float = 0.30
    confirmations: int = 2
    independent_audits: bool = False

    def __post_init__(self):
        if not 0 < self.surprise_likelihood < 0.5 or not 1 <= self.confirmations <= 6:
            raise ValueError("invalid change-point rules")


class RevisionAgent(EvidenceAgent):
    """Revises *source priors* after repeated contradictions of calibrated trust."""

    def __init__(self, policy: EvidencePolicy, rules: RevisionRules, state: dict | None = None):
        super().__init__(policy, state=state)
        self.rules = rules
        self.source_surprises = dict(state.get("source_surprises", {"A": 0, "B": 0})) if state else {"A": 0, "B": 0}
        self.revisions = list(state.get("revisions", [])) if state else []
        self.audit_checks = int(state.get("audit_checks", 0)) if state else 0

    def snapshot(self) -> dict:
        out = super().snapshot()
        out.update({
            "source_surprises": dict(self.source_surprises),
            "revisions": list(self.revisions),
            "audit_checks": self.audit_checks,
        })
        return out

    def _calibrate(self, readings: dict[str, int], truth: int, step: int):
        previous = {name: self.source_accuracy(name) for name in ("A", "B")}
        super()._calibrate(readings, truth, step)
        if not self.rules.enabled:
            return
        for name in ("A", "B"):
            value = readings.get(name)
            if value is None:
                continue
            matched = int(value == truth)
            prior = previous[name]
            probability = prior if matched else 1 - prior
            if probability < self.rules.surprise_likelihood:
                self.source_surprises[name] += 1
            else:
                self.source_surprises[name] = 0
            if self.source_surprises[name] >= self.rules.confirmations:
                # Retain the *historical evidence record*, but mark its old
                # reliability estimate as no longer governing current claims.
                self.reliability[name] = [2.0 + matched, 1.0 + (1 - matched)]
                self.source_surprises[name] = 0
                event = {
                    "source": name, "step": step,
                    "prior_trust": round(prior, 4), "latest_match": matched,
                    "reason": "repeated_out_of_model_verification",
                }
                self.revisions.append(event)
                self._hypothesis(
                    f"source_{name}_changed",
                    f"Source {name} reliability may have changed since the learned baseline",
                    step, f"verified:revision:{name}:{step}",
                    f"Future verified observations consistently support the old source {name} estimate",
                )

    def observe(self, step: int, readings: dict[str, int], verify, *, independent_audit: bool = False) -> dict:
        result = super().observe(step, readings, verify)
        # This audit opportunity is selected externally with a fixed random
        # schedule derived from its own stream, not from the observed truth.
        if not independent_audit or not self.rules.independent_audits:
            return result
        if result["action"] == "verify" or self.probes >= self.policy.max_probes:
            return result
        confirmed = int(verify())
        if confirmed not in (0, 1):
            raise ValueError("invalid independent audit result")
        prior = self.belief
        self.probes += 1
        self.audit_checks += 1
        if confirmed == prior:
            self.false_probes += 1
        else:
            self.belief = confirmed
            if self.detected_at is None:
                self.detected_at = step
        self._calibrate(readings, confirmed, step)
        self.evidence.append({
            "step": step, "reason": "independently_sampled_audit",
            "readings": dict(readings), "prior_belief": prior,
            "verified_state": confirmed, "estimate_before_verification": result["estimate"],
        })
        self._streak = 0
        return {"step": step, "action": "verify", "reason": "independently_sampled_audit",
                "belief": self.belief, "estimate": result["estimate"],
                "open_hypotheses": len(self.hypotheses)}


POLICY = EvidencePolicy(
    attention_threshold=0.45, probe_confidence=0.53, max_probes=4,
    min_persistence=3, reliability_decay=0.90, independent_check_period=0,
)


def evaluate_history(profiles: list[str], seeds: list[int], rules: RevisionRules, *,
                     carry_model: bool = True) -> dict:
    if not profiles or len(profiles) != len(seeds):
        raise ValueError("same nonzero number of profiles and seeds required")

    last_model = None
    rows = []
    error_sum = 0.0
    forecast_count = 0
    saved_count = 0
    for index, (profile, seed) in enumerate(zip(profiles, seeds)):
        case = case_for(seed, profile)
        agent = RevisionAgent(POLICY, rules)
        if carry_model and last_model:
            agent.reliability = {name: list(values) for name, values in last_model["reliability"].items()}
            agent.source_surprises = dict(last_model["source_surprises"])

        # The independent-audit schedule is generated separately from sensor
        # and state RNG; no ground-truth value affects this sampling decision.
        audit_step = random.Random(seed ^ 0x5F91E0).randrange(1, 12)
        for step, (a, b, truth) in enumerate(case["timeline"]):
            agent.observe(step, {"A": a, "B": b}, lambda value=truth: value,
                          independent_audit=(step == audit_step))
            predicted = agent.forecasts[-1]["p_state_1"]
            error_sum += (predicted - truth) ** 2
            forecast_count += 1
            if step == 6:
                snap = json.loads(json.dumps(agent.snapshot()))
                agent = RevisionAgent(POLICY, rules, state=snap)
                saved_count += int(agent.snapshot() == snap)
        if carry_model:
            last_model = {
                "reliability": {name: list(v) for name, v in agent.reliability.items()},
                "source_surprises": dict(agent.source_surprises),
            }
        hit = bool(case["changed"] and agent.belief == 1 and agent.detected_at is not None)
        if case["changed"]:
            pts = 4.0 - 0.2 * max(0, agent.detected_at - case["change_at"]) if hit else -2.0
        else:
            pts = 3.0 if agent.belief == 0 else -3.0
        pts -= 0.17 * agent.probes + 0.45 * agent.false_probes
        rows.append({
            "episode": index, "profile": profile,
            "changed": bool(case["changed"]), "hit": hit,
            "score": pts, "probes": agent.probes,
            "false_probes": agent.false_probes,
            "audits": agent.audit_checks,
            "revisions": len(agent.revisions),
            "trust_A": agent.source_accuracy("A"),
            "trust_B": agent.source_accuracy("B"),
        })

    def metrics(section):
        changes = sum(r["changed"] for r in section)
        hits = sum(r["hit"] for r in section)
        n = len(section)
        return {
            "episodes": n,
            "change_recall": round(hits / changes, 4) if changes else None,
            "mean_score": round(sum(r["score"] for r in section) / n, 4),
            "mean_probes": round(sum(r["probes"] for r in section) / n, 4),
            "mean_false_probes": round(sum(r["false_probes"] for r in section) / n, 4),
            "model_revisions": sum(r["revisions"] for r in section),
            "independent_audits": sum(r["audits"] for r in section),
        }

    middle = max(1, len(rows) // 2)
    return {
        "overall": metrics(rows),
        "first_half": metrics(rows[:middle]),
        "second_half": metrics(rows[middle:]),
        "brier": round(error_sum / forecast_count, 4),
        "restart_state_retained": saved_count,
        "end_trust": {"A": round(rows[-1]["trust_A"], 4), "B": round(rows[-1]["trust_B"], 4)},
        "early_episode_examples": [{**r, "score": round(r["score"], 4)} for r in rows[:3]],
        "late_episode_examples": [{**r, "score": round(r["score"], 4)} for r in rows[-3:]],
    }


def run_study() -> dict:
    # New seed window was not used to train Lab 003 or previous Lab 003b.
    seeds = list(range(47000, 47080))
    worlds = {
        "always_normal": ["standard"] * len(seeds),
        "always_stuck_B": ["stuck_b"] * len(seeds),
        "always_inverted_A": ["drifting_a"] * len(seeds),
        "stuck_B_then_normal": ["stuck_b"] * 40 + ["standard"] * 40,
        "normal_then_stuck_B": ["standard"] * 40 + ["stuck_b"] * 40,
        "alternating_10": [("stuck_b" if (i // 10) % 2 else "standard") for i in range(len(seeds))],
    }
    comparisons = {
        "remember_without_revision": RevisionRules(enabled=False),
        "revision_after_two_surprises": RevisionRules(),
        "revision_with_blind_audits": RevisionRules(independent_audits=True),
        "fresh_each_episode": RevisionRules(enabled=False),
    }
    return {
        "label": "BEAN_LAB004_CHANGE_POINT_SYNTHETIC_ONLY",
        "seed_window": [seeds[0], seeds[-1]],
        "profiles": list(worlds),
        "controller": asdict(POLICY),
        "revisions": {k: asdict(v) for k, v in comparisons.items()},
        "results": {
            scenario: {
                method: evaluate_history(
                    profiles, seeds, rules, carry_model=method != "fresh_each_episode"
                )
                for method, rules in comparisons.items()
            } for scenario, profiles in worlds.items()
        },
        "limitations": [
            "A two-sensor binary state simulation cannot establish broad reasoning or AGI.",
            "All truth is available only through explicitly metered synthetic inspection callbacks.",
            "Independent sampling opportunities are unrelated to the evaluator's event time.",
            "Verification selection bias remains a risk for error-triggered checks.",
            "Performance must be judged on all scenarios, including regressions and false revisions.",
            "No code is merged to BEAN or Bridge main by this research.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("bean-lab004-report.json"))
    args = parser.parse_args()
    body = json.dumps(run_study(), indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body + "\n", encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
