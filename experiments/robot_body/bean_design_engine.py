"""BEAN Design Engine: topology-neutral proposal, evidence, selection and revision.

Pure Python orchestration. Adapters must supply measured simulation/CAD results.
No model-generated claim is treated as evidence without an evaluator result.
"""
from dataclasses import dataclass, asdict
from typing import Callable
import json
from pathlib import Path

@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    topology: str
    parameters: dict
    parent_id: str | None = None
    rationale: str = ""

@dataclass(frozen=True)
class Evaluation:
    candidate_id: str
    feasible: bool
    metrics: dict
    evidence: dict
    failure: str | None = None

class DesignEngine:
    """BEAN owns the iterative design policy; physics/CAD are replaceable adapters."""
    def __init__(self, propose: Callable, evaluate: Callable, revise: Callable,
                 objectives: dict, max_evaluations: int = 32):
        if max_evaluations < 1:
            raise ValueError("max_evaluations must be positive")
        if not objectives or any(direction not in ("min", "max") for direction in objectives.values()):
            raise ValueError("objectives must map metric names to min/max")
        self.propose, self.evaluate, self.revise = propose, evaluate, revise
        self.objectives, self.max_evaluations = objectives, max_evaluations
        self.history = []

    def dominates(self, a: Evaluation, b: Evaluation) -> bool:
        if not a.feasible: return False
        if not b.feasible: return True
        try:
            comparisons = [(a.metrics[k] <= b.metrics[k] if direction == "min"
                            else a.metrics[k] >= b.metrics[k],
                            a.metrics[k] < b.metrics[k] if direction == "min"
                            else a.metrics[k] > b.metrics[k])
                           for k, direction in self.objectives.items()]
        except (KeyError, TypeError):
            return False
        return all(ok for ok, _ in comparisons) and any(better for _, better in comparisons)

    def frontier(self):
        valid = [e for _, e in self.history if e.feasible and
                 all(k in e.metrics and isinstance(e.metrics[k], (int, float))
                     for k in self.objectives)]
        return [e for e in valid if not any(self.dominates(other, e) for other in valid
                                             if other.candidate_id != e.candidate_id)]

    def run(self, initial: list[Candidate], out: Path | None = None):
        queue = list(initial)
        seen = set()
        while len(self.history) < self.max_evaluations:
            if not queue:
                proposed = self.propose(self.history, self.frontier())
                if proposed is None: break
                queue.extend(proposed if isinstance(proposed, list) else [proposed])
                if not queue: break
            candidate = queue.pop(0)
            if candidate.candidate_id in seen: continue
            seen.add(candidate.candidate_id)
            try:
                result = self.evaluate(candidate)
                if result.candidate_id != candidate.candidate_id:
                    raise ValueError("evaluation candidate ID mismatch")
                if result.feasible and not result.evidence:
                    raise ValueError("feasible evaluation requires evidence")
            except Exception as exc:
                result = Evaluation(candidate.candidate_id, False, {}, {},
                                    f"evaluator_error: {exc}")
            self.history.append((candidate, result))
            if result.feasible:
                revisions = self.revise(candidate, result, self.history, self.frontier())
                if revisions:
                    queue.extend(revisions if isinstance(revisions, list) else [revisions])
        report = {"objectives": self.objectives,
                  "evaluations": [{"candidate": asdict(c), "result": asdict(e)}
                                  for c, e in self.history],
                  "pareto_frontier": [asdict(e) for e in self.frontier()],
                  "status": "evaluation_records_only_not_hardware_validated"}
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2))
        return report
