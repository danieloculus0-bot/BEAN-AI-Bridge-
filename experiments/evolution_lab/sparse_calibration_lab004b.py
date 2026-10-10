"""BEAN Lab004b: pre-select calibration frequency on training-only worlds.

An independent verifier is informative, but each inspection is expensive.
Compare sparse independently sampled audits with continual audits, no audits,
and unchanged priors. The search never reads its separate evaluation seeds.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from experiments.evolution_lab.model_revision_lab004 import RevisionRules, evaluate_history


AUDIT_RATES = (0.0, 0.15, 0.30, 0.50, 0.75, 1.0)


def worlds_for(n: int) -> dict[str, list[str]]:
    halfway = n // 2
    return {
        "normal": ["standard"] * n,
        "failed_B": ["stuck_b"] * n,
        "failed_A": ["drifting_a"] * n,
        "failed_B_then_normal": ["stuck_b"] * halfway + ["standard"] * (n - halfway),
        "normal_then_failed_B": ["standard"] * halfway + ["stuck_b"] * (n - halfway),
        "alternating": ["stuck_b" if (i // 10) % 2 else "standard" for i in range(n)],
    }


def select_frequency() -> tuple[RevisionRules, list[dict]]:
    seeds = list(range(51000, 51040))
    profiles = worlds_for(len(seeds))
    scores = []
    for rate in AUDIT_RATES:
        rules = RevisionRules(independent_audits=(rate > 0), audit_probability=rate)
        by_world = {
            name: evaluate_history(series, seeds, rules)["overall"]["mean_score"]
            for name, series in profiles.items()
        }
        scores.append({
            "audit_probability": rate,
            "mean_training_score": round(sum(by_world.values()) / len(by_world), 4),
            "by_training_world": by_world,
        })
    scores.sort(key=lambda r: (-r["mean_training_score"], r["audit_probability"]))
    chosen = scores[0]
    return RevisionRules(
        independent_audits=chosen["audit_probability"] > 0,
        audit_probability=chosen["audit_probability"],
    ), scores


def run_study() -> dict:
    chosen, selection = select_frequency()
    seeds = list(range(62000, 62120))
    scenarios = worlds_for(len(seeds))
    policies = {
        "trained_frequency": chosen,
        "no_independent_audits": RevisionRules(),
        "every_episode_audit": RevisionRules(independent_audits=True),
        "no_revisions": RevisionRules(enabled=False),
    }
    results = {
        world: {
            name: evaluate_history(sequence, seeds, rule)
            for name, rule in policies.items()
        } | {"fresh_each_time": evaluate_history(sequence, seeds,
                                             RevisionRules(enabled=False),
                                             carry_model=False)}
        for world, sequence in scenarios.items()
    }
    comparisons = {
        method: {
            "average_holdout_score": round(
                sum(group[method]["overall"]["mean_score"] for group in results.values()) / len(results), 4
            ),
            "average_holdout_recall": round(
                sum(group[method]["overall"]["change_recall"] for group in results.values()) / len(results), 4
            ),
            "average_brier": round(
                sum(group[method]["brier"] for group in results.values()) / len(results), 4
            ),
            "total_model_revisions": sum(group[method]["overall"]["model_revisions"] for group in results.values()),
        }
        for method in list(policies) + ["fresh_each_time"]
    }
    return {
        "label": "LAB004B_SPARSE_CALIBRATION_RESEARCH_NOT_AGI",
        "train_seed_window": [51000, 51039],
        "holdout_seed_window": [62000, 62119],
        "selected_rules": asdict(chosen),
        "training_candidates": selection,
        "methods": {name: asdict(r) for name, r in policies.items()},
        "aggregates": comparisons,
        "by_world": results,
        "interpretation_limits": [
            "Selection optimized synthetic mean score only; this is not online self-modification.",
            "Audit scheduling is reproducibly random and independent of sensor evidence.",
            "Changes in recall, calibration error and false alarms can conflict.",
            "This result is not generalizable to live hardware or economic decisions.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("bean-lab004b-report.json"))
    args = parser.parse_args()
    body = json.dumps(run_study(), indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body + "\n", encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
