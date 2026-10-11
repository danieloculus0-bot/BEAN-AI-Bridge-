"""Lab 014: conservative recovery from changed and repaired evidence sources.

Research-only; neither a live model nor production BEAN policy is altered.
Uses Lab 013's independent audit receipts, frozen policy catalogue, and evaluator.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from .lab012 import DOMAINS, Policy, scenario
from .lab013 import (
    AdaptiveLearner, LearningParameters, _fingerprint, action_reward,
    policy_catalogue, ranking,
)

# Both candidates have the same independent audit expenditure.
FROZEN_CONTROLS = LearningParameters(
    audits_per_world=2, evidence_window=16, minimum_audits=28,
    advantage_margin=.75, confirm_windows=2, cooldown_worlds=8,
    max_policy_changes=6,
)


@dataclass(frozen=True)
class RecoveryControls:
    recent_worlds: int = 18
    confirmation: int = 2
    standard_error_multiplier: float = 0.7
    minimum_lift: float = 0.5
    cooldown: int = 8
    maximum_switches: int = 6

    def __post_init__(self):
        if not 8 <= self.recent_worlds <= 48:
            raise ValueError("recent_worlds must be 8..48")
        if not 1 <= self.confirmation <= 5:
            raise ValueError("confirmation must be 1..5")
        if not 0 <= self.standard_error_multiplier <= 3:
            raise ValueError("standard_error_multiplier must be 0..3")
        if not 0 < self.minimum_lift <= 5:
            raise ValueError("minimum_lift must be >0 and <=5")
        if not 0 <= self.cooldown <= 40 or not 0 <= self.maximum_switches <= 20:
            raise ValueError("invalid cooldown or switch cap")


def paired_advantage(history: list[dict], challenger: str, incumbent: str) -> dict:
    """Unbiased paired HT estimate and descriptive sampling SE.

    A normal-theory bound is a heuristic, *not* a calibrated confidence interval.
    World-level clustering is preserved by computing contributions per world.
    """
    samples = []
    distinct = 0
    for row in history:
        lhs = set(row["selections"][challenger])
        rhs = set(row["selections"][incumbent])
        if lhs == rhs:
            samples.append(0.0)
            continue
        distinct += 1
        value = sum(
            ((item["id"] in lhs) - (item["id"] in rhs)) *
            (6 if item["truth"] else -2) / row["sample_probability"]
            for item in row["audits"]
        )
        samples.append(value)
    n = len(samples)
    mean = sum(samples) / n if n else 0.0
    se = (statistics.stdev(samples) / math.sqrt(n)) if n > 1 else None
    return {"mean_advantage": round(mean, 6),
            "standard_error": round(se, 6) if se is not None else None,
            "worlds": n, "distinct_policy_choices": distinct}


class RecoveryLearner(AdaptiveLearner):
    """Use only auditor-observed feedback to propose conservative revisions."""

    def __init__(self, catalogue: dict[str, Policy], controls: RecoveryControls):
        super().__init__(catalogue, FROZEN_CONTROLS)
        self.recovery_controls = controls

    def _review(self):
        c = self.recovery_controls
        if self.world_index < c.recent_worlds or self.world_index < self.cooldown_until:
            return
        if len(self.transitions) >= c.maximum_switches:
            return
        window = self.history[-c.recent_worlds:]
        options = []
        for name in sorted(self.catalogue):
            if name == self.current:
                continue
            estimate = paired_advantage(window, name, self.current)
            if estimate["standard_error"] is None:
                continue
            lower = estimate["mean_advantage"] - (
                c.standard_error_multiplier * estimate["standard_error"])
            options.append((lower, name, estimate))
        if not options:
            return
        # Policy names are used only for deterministic ties.
        lower, candidate, estimate = sorted(options, key=lambda x: (-x[0], x[1]))[0]
        if lower <= c.minimum_lift:
            self.pending = None
            self.pending_count = 0
            return
        if candidate == self.pending:
            self.pending_count += 1
        else:
            self.pending, self.pending_count = candidate, 1
        if self.pending_count < c.confirmation:
            return
        before = self.current
        evidence = [row["sha256"] for row in window]
        event = {
            "event": "rollback" if candidate in self.retired else "proposed_revision",
            "world": self.world_index, "from": before, "to": candidate,
            "estimated_advantage_per_world": estimate["mean_advantage"],
            "estimated_standard_error": estimate["standard_error"],
            "conservative_lower_estimate": round(lower, 6),
            "uncertainty_method": "world_clustered_descriptive_SE",
            "confidence_calibrated": False,
            "cause_hypothesis": "Policy ranking has changed under independent audits",
            "investigation": self._investigate(window),
            "evidence_ids": evidence,
            "evidence_count": sum(len(row["audits"]) for row in window),
            "rollback_to": before,
            "simulation_only": True,
            "provenance": "uniform_audit_counterfactuals",
        }
        event["sha256"] = _fingerprint(event)
        self.transitions.append(event)
        self.retired.append(before)
        self.previous = before
        self.current = candidate
        self.pending = None
        self.pending_count = 0
        self.cooldown_until = self.world_index + c.cooldown

    def export_state(self) -> dict:
        snapshot = super().export_state()
        # Keep the inherited checkable state; do not claim the controls are
        # persisted by this experimental serialization contract.
        return snapshot


def episodes(domain: str, *, training: bool, pattern: str) -> list[tuple[str, int, bool]]:
    if pattern not in {"stable", "reversal", "repeat"}:
        raise ValueError("unsupported pattern")
    root = (14000 if training else 83000) + {"reversal": 0, "stable": 10000, "repeat": 20000}[pattern]
    if training:
        durations = {"normal": 20, "changed": 34, "recovered": 24, "changed_again": 24}
    else:
        durations = {"normal": 28, "changed": 42, "recovered": 34, "changed_again": 34}
    if pattern == "stable":
        durations = {"normal": sum(durations.values())}
    elif pattern == "reversal":
        durations = {k: v for k, v in durations.items() if k != "changed_again"}
    elif pattern != "repeat":
        raise ValueError("unsupported pattern")
    records = []
    for position, (stage, count) in enumerate(durations.items()):
        for number in range(count):
            # Disjoint from all Lab 012 and Lab 013 training/holdouts.
            seed = root + position * 1000 + number
            records.append((stage, seed, stage.startswith("changed")))
    return records


def replay(domain: str, catalogue: dict[str, Policy],
           controls: RecoveryControls, *, training: bool, pattern: str) -> dict:
    original = AdaptiveLearner(catalogue, FROZEN_CONTROLS)
    candidate = RecoveryLearner(catalogue, controls)
    phases: dict[str, dict] = {}
    first_switch: dict[str, dict] = {}
    for stage, seed, changed in episodes(domain, training=training, pattern=pattern):
        world = scenario(domain, seed, shifted=changed)
        visible = [{"id": x["id"], "features": x["features"]} for x in world]
        if stage not in phases:
            phases[stage] = {"worlds": 0, "frozen_reward": 0, "lab013_reward": 0,
                             "lab014_reward": 0, "lab013_changes": 0, "lab014_changes": 0}
        baseline = ranking(visible, catalogue["broad"])
        old_action = original.act(visible)
        new_action = candidate.act(visible)
        phase = phases[stage]
        phase["worlds"] += 1
        phase["frozen_reward"] += action_reward(baseline, world)
        phase["lab013_reward"] += action_reward(old_action, world)
        phase["lab014_reward"] += action_reward(new_action, world)
        # Uniform auditing is explicitly independent of rank, truth, choice and stage.
        rng = random.Random(f"lab014:independent:{domain}:{seed}")
        sampled = rng.sample(world, FROZEN_CONTROLS.audits_per_world)
        verified = [{"id": row["id"], "truth": row["truth"]} for row in sampled]
        old_changes = len(original.transitions)
        new_changes = len(candidate.transitions)
        original.ingest_audit(visible, verified)
        candidate.ingest_audit(visible, verified)
        if len(original.transitions) > old_changes:
            phase["lab013_changes"] += 1
        if len(candidate.transitions) > new_changes:
            phase["lab014_changes"] += 1
            first_switch.setdefault(stage, {
                "world_in_stage": phase["worlds"],
                "transition": candidate.transitions[-1]["event"],
                "from": candidate.transitions[-1]["from"],
                "to": candidate.transitions[-1]["to"],
            })
    regressions = []
    for stage, info in phases.items():
        n = info["worlds"]
        for policy in ("frozen", "lab013", "lab014"):
            info[policy + "_per_world"] = round(info.pop(policy + "_reward") / n, 6)
        info["candidate_vs_lab013"] = round(info["lab014_per_world"] - info["lab013_per_world"], 6)
        info["candidate_vs_frozen"] = round(info["lab014_per_world"] - info["frozen_per_world"], 6)
        if info["candidate_vs_lab013"] < -0.75:
            regressions.append({"domain": domain, "phase": stage,
                                "delta": info["candidate_vs_lab013"]})
    # Identical audit expenditure; report it anyway for interpretation.
    audits = candidate.snapshot()["independent_audits"]
    assert audits == original.snapshot()["independent_audits"]
    return {"domain": domain, "pattern": pattern, "phases": phases,
            "candidate_switches": len(candidate.transitions),
            "original_switches": len(original.transitions),
            "first_switch_by_phase": first_switch,
            "candidate_rollback_count": sum(row["event"] == "rollback" for row in candidate.transitions),
            "independent_audits_per_policy": audits,
            "audit_cost_each": round(audits * .15, 4),
            "regressions": regressions,
            "last_policy": candidate.current,
            "events": candidate.transitions}


def _evaluate(controls: RecoveryControls, catalogue: dict[str, Policy],
              *, training: bool) -> dict:
    sims = [replay(d, catalogue, controls, training=training, pattern=mode)
            for mode in ("reversal", "stable", "repeat") for d in DOMAINS]
    advantage = sum(sum(info["candidate_vs_lab013"] * info["worlds"]
                        for info in sim["phases"].values()) for sim in sims)
    harms = [item for sim in sims for item in sim["regressions"]]
    total_worlds = sum(sum(info["worlds"] for info in sim["phases"].values()) for sim in sims)
    return {"results": sims, "reward_delta_vs_equal_audit_lab013": round(advantage, 5),
            "mean_reward_delta": round(advantage / total_worlds, 6),
            "worlds": total_worlds, "regressions": harms,
            "rollback_events": sum(sim["candidate_rollback_count"] for sim in sims),
            "switches": sum(sim["candidate_switches"] for sim in sims)}


def run() -> dict:
    catalogue = policy_catalogue()
    # PRE-REGISTERED finite candidates, selected exclusively on new training
    # seeds. Prior Labs 012/013 holdout seeds are not consulted.
    choices = [
        RecoveryControls(),
        RecoveryControls(recent_worlds=12, confirmation=2,
                         standard_error_multiplier=.35, minimum_lift=.6, cooldown=6),
        RecoveryControls(recent_worlds=24, confirmation=3,
                         standard_error_multiplier=1.0, minimum_lift=.35, cooldown=10),
    ]
    training = [_evaluate(x, catalogue, training=True) for x in choices]
    # Prefer reward, penalize dangerous stage regression on TRAIN only.
    train_scores = [round(item["reward_delta_vs_equal_audit_lab013"] -
                          40 * len(item["regressions"]), 5) for item in training]
    index = max(range(len(choices)), key=lambda i: (train_scores[i], -i))
    final = _evaluate(choices[index], catalogue, training=False)
    # This stricter gate prevents aggregate improvements hiding severe failures.
    pass_gate = (final["reward_delta_vs_equal_audit_lab013"] > 0
                 and not final["regressions"]
                 and final["rollback_events"] >= 1)
    return {
        "schema": "bean.lab014.v1", "synthetic_only": True,
        "baseline": "frozen_lab013_equal_uniform_audit_budget",
        "catalogue": {name: list(policy.weights) for name, policy in catalogue.items()},
        "training_seed_bases": [14000, 24000, 34000],
        "new_holdout_seed_bases": [83000, 93000, 103000],
        "selection_scores_train_only": train_scores,
        "chosen_index": index, "chosen_controls": asdict(choices[index]),
        "holdout": final, "verdict": (
            "RECOVERY_GENERALIZATION_DEMONSTRATED_IN_SYNTHETIC_LAB"
            if pass_gate else "RECOVERY_GENERALIZATION_NOT_DEMONSTRATED"),
        "limits": [
            "Simulation and canned policy catalogue, not open-ended autonomous self-improvement.",
            "Comparator and learner consume identical independent audits.",
            "Normal-theory standard error is an uncalibrated descriptive bound.",
            "No real hardware, web, ERP, inference-provider or production policy changes.",
            "Evaluation seeds are separated but the grading code is not secret."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("lab014.json"))
    args = parser.parse_args()
    result = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {"verdict": result["verdict"], "chosen_controls": result["chosen_controls"],
               **{k: result["holdout"][k] for k in
                  ("worlds", "reward_delta_vs_equal_audit_lab013",
                   "mean_reward_delta", "rollback_events", "switches", "regressions")}}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
