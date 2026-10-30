"""Wire Core curiosity and goals to Bridge tool choice, feedback and memory.

Core owns observations, goals and autobiographical events. Bridge owns the
module registry, execution, policy selection and outcome ledger. This adapter
is the point where previously disconnected subsystems exchange real data.
"""
from __future__ import annotations

import json
import random

from .modules import BlockRuntime

SCHEMA = "bean.cognition.experiment.v1"


class CognitiveDispatcher:
    """Turn observed questions into executed, outcome-scored tool experiments."""

    def __init__(self, modules: BlockRuntime):
        self.modules = modules

    @staticmethod
    def _experiment_questions():
        from bean.memory.store import get_store

        rows = get_store().fetchall(
            "SELECT id, question, context FROM curiosity "
            "WHERE status='open' ORDER BY id"
        )
        eligible = []
        for row in rows:
            try:
                spec = json.loads(row["context"] or "{}")
            except (ValueError, TypeError):
                continue
            if (
                isinstance(spec, dict) and spec.get("schema") == SCHEMA
                and isinstance(spec.get("capability"), str)
                and isinstance(spec.get("inputs"), dict)
                and isinstance(spec.get("expected_output"), dict)
            ):
                eligible.append(dict(row))
        return eligible

    def poll(self, session_uuid: str, *, max_goals: int = 1) -> list[dict]:
        """Run local experiments on each call; suitable for the Core tick loop.

        A negative result is still a useful, recorded experience. No provider
        key or hosted model is necessary for ordinary logic experiments.
        """
        from bean.cognition.goal_state import GoalStateEngine, ActionType
        from bean.cognition.consolidation import ConsolidationEngine
        from bean.memory.event_logger import EventType, Source, log_event
        from bean.memory.store import get_store

        goal_engine = GoalStateEngine()
        questions = self._experiment_questions()
        if questions:
            goal_engine.propose(session_uuid, [], questions)

        pending = [
            goal for goal in goal_engine.get_pending(session_uuid)
            if goal.action_type == ActionType.RUN_EXPERIMENT
        ]
        results = []
        for goal in pending[:max_goals]:
            detail = goal.action_detail or {}
            question_id = detail["question_id"]
            current = get_store().fetchone(
                "SELECT status FROM curiosity WHERE id=?", (question_id,)
            )
            if current is None or current["status"] != "open":
                goal_engine.complete(goal.proposal_id, "Question already resolved")
                continue
            capability = detail["capability"]
            try:
                trial = self.modules.run(
                    capability, detail["inputs"], explore=True,
                    rng=random.Random(question_id + len(results)),
                    context={"session_uuid": session_uuid},
                )
                actual = trial["output"]
                expected = detail["expected_output"]
                matched = all(actual.get(k) == v for k, v in expected.items())
                reward = 1.0 if matched else -1.0
                preference = self.modules.feedback(trial["run_id"], reward)
                outcome = {
                    "question_id": question_id,
                    "goal_id": goal.proposal_id,
                    "capability": capability, "block": trial["block"],
                    "run_id": trial["run_id"], "revision": trial["revision"],
                    "output": actual, "observed": expected, "matched": matched,
                    "reward": reward, "preference": preference,
                }
                log_event(
                    session_uuid, EventType.OBSERVATION,
                    f"Bridge tested {trial['block']}; observed match={matched}.",
                    Source.SYSTEM, subtype="cognitive_module_experiment",
                    data=outcome,
                )
                answer = (
                    f"Experiment {trial['run_id']}: {trial['block']} returned "
                    f"{json.dumps(actual, sort_keys=True)}; observed "
                    f"{json.dumps(expected, sort_keys=True)}; "
                    f"match={matched}. A single trial does not prove generalization."
                )
                log_event(
                    session_uuid, EventType.FACT_LEARNED,
                    f"Observed result for question {question_id}.",
                    Source.SYSTEM, subtype="experiment_result",
                    data={"question_id": question_id, "answer": answer,
                          "run_id": trial["run_id"]},
                )
                ConsolidationEngine()._close_resolved_questions(session_uuid)
                goal_engine.complete(goal.proposal_id, "Observed trial: " + trial["run_id"])
                results.append(outcome)
            except Exception as exc:
                # BlockRuntime independently records module errors and negative
                # outcome feedback. Preserve the Core-side goal attempt too.
                log_event(
                    session_uuid, EventType.ERROR,
                    f"Experimental module for {capability} failed: {exc}",
                    Source.SYSTEM, subtype="cognitive_module_failure",
                    data={"question_id": question_id, "goal_id": goal.proposal_id,
                          "capability": capability, "error_type": type(exc).__name__},
                )
                goal_engine.complete(goal.proposal_id, f"Trial failed: {type(exc).__name__}")
                results.append({
                    "question_id": question_id,
                    "goal_id": goal.proposal_id,
                    "capability": capability,
                    "status": "experiment_error",
                    "error_type": type(exc).__name__,
                })
        return results


def make_tick_handler(dispatcher: CognitiveDispatcher, *, interval: int = 10):
    """Bridge can be registered on the existing Core tick scheduler."""
    def tick(tick_number: int, session_uuid: str, context: dict):
        return dispatcher.poll(session_uuid)

    return tick
