"""Run BEAN's design engine against actual MuJoCo quadruped physics.

This is the first live engine integration. Cross-topology CAD adapters are future work.
"""
import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from bean_design_engine import Candidate, DesignEngine, Evaluation
from lab import Design, run_physics

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("robot-results/engine.json"))
    p.add_argument("--budget", type=int, default=12)
    args = p.parse_args()
    baseline = Design()
    initial = [Candidate("baseline", "quadruped", asdict(baseline), rationale="Fixed lab 001 baseline")]
    steps = [(-.005, .004, .04), (.005, -.004, -.04), (.0, .002, .08)]
    counter = [0]

    def propose(history, frontier):
        return None

    def evaluate(candidate):
        if candidate.topology != "quadruped":
            return Evaluation(candidate.candidate_id, False, {}, {}, "No physics adapter for topology")
        d = Design(**candidate.parameters)
        metrics = run_physics(d, duration=3.0)
        return Evaluation(candidate.candidate_id, not metrics["fell"],
                          {"forward_m": metrics["forward_m"],
                           "energy_j": metrics["energy_j"],
                           "max_tilt_rad": metrics["max_tilt_rad"]},
                          {"engine": "MuJoCo", "duration_s": 3.0, "raw": metrics})

    def revise(candidate, result, history, frontier):
        if not result.feasible or counter[0] >= args.budget - 1:
            return []
        # Deterministic local exploration; each trial is genuinely evaluated by MuJoCo.
        d = Design(**candidate.parameters)
        revisions = []
        for dl, dc, df in steps:
            if counter[0] >= args.budget - 1:
                break
            counter[0] += 1
            nxt = replace(d, stride=max(.02, min(.07, d.stride + dl)),
                          clearance=max(.012, min(.042, d.clearance + dc)),
                          frequency=max(.6, min(1.55, d.frequency + df)))
            revisions.append(Candidate(f"revision-{counter[0]:03d}", "quadruped",
                                       asdict(nxt), parent_id=candidate.candidate_id,
                                       rationale="Deterministic gait perturbation"))
        return revisions

    engine = DesignEngine(propose, evaluate, revise,
                          {"forward_m": "max", "energy_j": "min", "max_tilt_rad": "min"},
                          max_evaluations=args.budget)
    report = engine.run(initial, args.out)
    print(json.dumps({"evaluated": len(report["evaluations"]),
                      "frontier": report["pareto_frontier"],
                      "artifact": str(args.out)}, indent=2))

if __name__ == "__main__":
    main()
