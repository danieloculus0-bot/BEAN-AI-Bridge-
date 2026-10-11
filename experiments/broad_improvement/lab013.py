"""Lab 013: audit-grounded adaptive learning over Lab 012 task families.

Never passes evaluator truth, phase labels or held-out rewards to the learner.
Only independent sampled audits enter its evidence history. All policy changes
are simulated; production BEAN Core remains proposal-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from .lab012 import BASELINE, DOMAINS, FEATURES, Policy, scenario, train


@dataclass(frozen=True)
class LearningParameters:
    # Four policy weights are optimized by Lab 012. These seven behavioral
    # controls are tuned separately, against training-only world sequences.
    audits_per_world: int = 3
    evidence_window: int = 20
    minimum_audits: int = 36
    advantage_margin: float = 0.65
    confirm_windows: int = 2
    cooldown_worlds: int = 8
    max_policy_changes: int = 6

    def __post_init__(self):
        if not 1 <= self.audits_per_world <= 4:
            raise ValueError("audits_per_world must be in 1..4")
        if not 8 <= self.evidence_window <= 80:
            raise ValueError("evidence_window must be in 8..80")
        if not 1 <= self.minimum_audits <= self.evidence_window * self.audits_per_world:
            raise ValueError("invalid minimum_audits")
        if not 0 < self.advantage_margin <= 4:
            raise ValueError("invalid advantage_margin")
        if not 1 <= self.confirm_windows <= 6 or self.cooldown_worlds < 0:
            raise ValueError("invalid confirmation or cooldown")
        if not 0 <= self.max_policy_changes <= 20:
            raise ValueError("invalid max_policy_changes")


def ranking(observations: list[dict], policy: Policy, inspection_budget: int = 3) -> set[str]:
    return {item["id"] for item in sorted(
        observations, key=lambda item: (-policy.score(item["features"]), item["id"])
    )[:inspection_budget]}


def action_reward(selected: set[str], world: list[dict]) -> int:
    """For evaluator only. The learner never receives uninspected labels."""
    return sum(3 if item["truth"] and item["id"] in selected else
               -3 if item["truth"] else -2 if item["id"] in selected else 0
               for item in world)


def _fingerprint(evidence: dict) -> str:
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


class AdaptiveLearner:
    def __init__(self, catalogue: dict[str, Policy], parameters: LearningParameters,
                 initial: str = "broad"):
        if initial not in catalogue or len(set(p.weights for p in catalogue.values())) != len(catalogue):
            raise ValueError("Catalogue must contain unique policies and initial")
        self.catalogue = dict(catalogue)
        self.parameters = parameters
        self.current = initial
        self.history: list[dict] = []  # append-only, independently sampled verified evidence
        self.transitions: list[dict] = []
        self.previous: str | None = None
        self.pending: str | None = None
        self.pending_count = 0
        self.cooldown_until = 0
        self.world_index = 0
        self.retired: list[str] = []

    def act(self, observations: list[dict]) -> set[str]:
        if any("truth" in item or "phase" in item for item in observations):
            raise ValueError("Evaluator-only state must not reach learner")
        return ranking(observations, self.catalogue[self.current])

    def ingest_audit(self, observations: list[dict], verified: list[dict]) -> dict:
        """Receive uniformly sampled evidence only, with known propensity.

        A sampled truth label may not be copied from arbitrary caller data:
        exact observation IDs and sampled labels are both required.
        """
        p = self.parameters
        if len(verified) != p.audits_per_world:
            raise ValueError("incorrect independent audit count")
        by_id = {item["id"]: item for item in observations}
        ids = [item["id"] for item in verified]
        if len(ids) != len(set(ids)) or any(i not in by_id for i in ids):
            raise ValueError("audit IDs must be distinct observed IDs")
        if any(type(item.get("truth")) is not bool for item in verified):
            raise ValueError("verified labels must be bool")
        selections = {k: ranking(observations, policy) for k, policy in self.catalogue.items()}
        receipt = {
            "world": self.world_index,
            "sample_probability": p.audits_per_world / len(observations),
            "audits": [{"id": item["id"], "truth": item["truth"],
                        "features": by_id[item["id"]]["features"]} for item in verified],
            "selections": {name: sorted(selected) for name, selected in selections.items()},
        }
        receipt["sha256"] = _fingerprint(receipt)
        self.history.append(receipt)
        self.world_index += 1
        self._review()
        return {"evidence_id": receipt["sha256"], "audits": len(verified),
                "active": self.current}

    def _relative_reward(self, challenger: str, incumbent: str, records: list[dict]) -> float:
        """Paired Horvitz-Thompson estimate of challenger minus incumbent.

        The shared missed-positive term cancels, preventing selective sampling
        of high-confidence inspected items from silently becoming ground truth.
        """
        delta = 0.0
        for record in records:
            cand = set(record["selections"][challenger])
            base = set(record["selections"][incumbent])
            for item in record["audits"]:
                if item["id"] in cand or item["id"] in base:
                    delta += ((item["id"] in cand) - (item["id"] in base)) * (
                        (6 if item["truth"] else 0) - 2) / record["sample_probability"]
        return delta / len(records) if records else 0.0

    def _review(self):
        p = self.parameters
        if (len(self.transitions) >= p.max_policy_changes or
                self.world_index < self.cooldown_until):
            return
        window = self.history[-p.evidence_window:]
        if len(window) < p.evidence_window or sum(len(r["audits"]) for r in window) < p.minimum_audits:
            return
        alternatives = sorted(
            ((self._relative_reward(name, self.current, window), name)
             for name in self.catalogue if name != self.current),
            key=lambda x: (-x[0], x[1])
        )
        advantage, candidate = alternatives[0]
        if advantage <= p.advantage_margin:
            self.pending = None
            self.pending_count = 0
            return
        if candidate != self.pending:
            self.pending = candidate
            self.pending_count = 1
        else:
            self.pending_count += 1
        if self.pending_count < p.confirm_windows:
            return
        old = self.current
        is_rollback = candidate == self.previous
        evidence_ids = [r["sha256"] for r in window]
        event = {
            "event": "rollback" if is_rollback else "proposed_revision",
            "world": self.world_index, "from": old, "to": candidate,
            "estimated_advantage_per_world": round(advantage, 4),
            "cause_hypothesis": "Independent audits favor a different explanation/priority",
            "evidence_count": sum(len(r["audits"]) for r in window),
            "evidence_ids": evidence_ids,
            "rollback_to": old, "simulation_only": True,
            "provenance": "sampled_independent_audits",
        }
        event["sha256"] = _fingerprint(event)
        self.transitions.append(event)
        self.retired.append(old)
        self.previous = old
        self.current = candidate
        self.pending = None
        self.pending_count = 0
        self.cooldown_until = self.world_index + p.cooldown_worlds

    def snapshot(self) -> dict:
        return {
            "active_policy": self.current,
            "worlds_seen": self.world_index,
            "independent_audits": sum(len(x["audits"]) for x in self.history),
            "transition_count": len(self.transitions),
            "transitions": self.transitions,
            "evidence_chain": [x["sha256"] for x in self.history],
            "retired_policies_preserved": list(self.retired),
        }


def policy_catalogue() -> dict[str, Policy]:
    """All policy alternatives learned from separate Lab012 training seeds."""
    choices = {"baseline": Policy(BASELINE), "broad": train(DOMAINS)[0]}
    for domain in DOMAINS:
        candidate = train((domain,))[0]
        if candidate.weights not in (policy.weights for policy in choices.values()):
            choices["trained_" + domain] = candidate
    return choices


def timeline(domain: str, *, training: bool) -> list[tuple[str, int, bool]]:
    if training:
        return ([("initial", 1200 + i, False) for i in range(18)] +
                [("changed", 2200 + i, True) for i in range(30)] +
                [("recovered", 3200 + i, False) for i in range(20)])
    return ([("initial", 41000 + i, False) for i in range(30)] +
            [("changed", 52000 + i, True) for i in range(50)] +
            [("recovered", 63000 + i, False) for i in range(30)])


def simulate(domain: str, catalogue: dict[str, Policy], parameters: LearningParameters,
             *, training: bool = False) -> dict:
    brain = AdaptiveLearner(catalogue, parameters)
    stages = {name: {"baseline": 0, "broad": 0, "adaptive": 0, "worlds": 0}
              for name in ("initial", "changed", "recovered")}
    for label, seed, shifted in timeline(domain, training=training):
        world = scenario(domain, seed, shifted=shifted)
        visible = [{"id": x["id"], "features": x["features"]} for x in world]
        chosen = brain.act(visible)
        baseline = ranking(visible, catalogue["baseline"])
        broad = ranking(visible, catalogue["broad"])
        stages[label]["baseline"] += action_reward(baseline, world)
        stages[label]["broad"] += action_reward(broad, world)
        stages[label]["adaptive"] += action_reward(chosen, world)
        stages[label]["worlds"] += 1
        # Explicitly independent of scores, actions, outcomes and phase name.
        rng = random.Random(f"lab013:unbiased:{domain}:{seed}")
        sampled = rng.sample(world, parameters.audits_per_world)
        brain.ingest_audit(visible, [{"id": x["id"], "truth": x["truth"]} for x in sampled])
    for item in stages.values():
        n = item["worlds"]
        for name in ("baseline", "broad", "adaptive"):
            item[name + "_reward_per_world"] = round(item[name] / n, 4)
            del item[name]
    return {"domain": domain, "stages": stages, "learning": brain.snapshot(),
            "audit_cost_units": round(brain.snapshot()["independent_audits"] * 0.15, 4)}


def run() -> dict:
    catalogue = policy_catalogue()
    # Controls are selected solely from training timeline; never test on
    # the final evaluation seeds until after the configuration is frozen.
    trials = [
        LearningParameters(),
        LearningParameters(audits_per_world=2, evidence_window=16, minimum_audits=28,
                           advantage_margin=0.75, confirm_windows=2, cooldown_worlds=8),
        LearningParameters(audits_per_world=4, evidence_window=24, minimum_audits=54,
                           advantage_margin=0.55, confirm_windows=2, cooldown_worlds=10),
    ]
    train_scores = []
    for params in trials:
        sims = [simulate(d, catalogue, params, training=True) for d in DOMAINS]
        benefit = sum(sum(stage["adaptive_reward_per_world"] - stage["broad_reward_per_world"]
                          for stage in simulation["stages"].values()) for simulation in sims)
        audit_cost = sum(x["audit_cost_units"] for x in sims)
        train_scores.append(round(benefit - audit_cost / sum(
            sum(stage["worlds"] for stage in sim["stages"].values()) for sim in sims), 4))
    selected = max(range(len(trials)), key=lambda i: (train_scores[i], -i))
    params = trials[selected]
    out = [simulate(d, catalogue, params) for d in DOMAINS]
    total_delta = 0.0
    regressions = []
    for sim in out:
        for phase, metrics in sim["stages"].items():
            delta = round(metrics["adaptive_reward_per_world"] - metrics["broad_reward_per_world"], 4)
            metrics["adaptive_vs_broad_delta"] = delta
            total_delta += delta * metrics["worlds"]
            if delta < -0.75:
                regressions.append({"domain": sim["domain"], "phase": phase, "delta": delta})
    total_audit_cost = sum(x["audit_cost_units"] for x in out)
    gain_net = round(total_delta - total_audit_cost, 4)
    verdict = ("BROAD_SELF_CORRECTION_EVIDENCE_IN_SYNTHETIC_LAB"
               if gain_net > 0 and not regressions and
               sum(bool(x["learning"]["transitions"]) for x in out) >= 3
               else "BROAD_SELF_CORRECTION_NOT_DEMONSTRATED")
    return {"schema": "bean.lab013.v1", "synthetic_only": True,
            "catalogue": {name: policy.weights for name, policy in catalogue.items()},
            "parameter_dimensions": ["four attention weights", *list(asdict(params))],
            "trial_training_scores": train_scores, "selected_trial": selected,
            "selected_parameters": asdict(params), "results": out,
            "net_gain": gain_net, "regressions": regressions, "verdict": verdict,
            "limitations": [
                "Independent audits have simulated oracle labels and explicit extra cost.",
                "Paired inverse-propensity estimates remain noisy and need confidence intervals.",
                "Candidate set and improvement controls are bounded, not arbitrary self-written code.",
                "Synthetic task families share the same four engineered features.",
                "No phase label or uninspected truth is passed to the learner.",
                "Simulated policy revisions are not permission to execute on a real host."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("lab013-results.json"))
    args = parser.parse_args()
    result = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"], "selected_parameters": result["selected_parameters"],
                      "net_gain": result["net_gain"], "regressions": result["regressions"],
                      "adaptations": {x["domain"]: x["learning"]["transition_count"] for x in result["results"]}}, indent=2))


if __name__ == "__main__":
    main()
