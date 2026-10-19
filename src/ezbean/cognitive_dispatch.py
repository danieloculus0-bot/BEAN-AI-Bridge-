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

    def _tried_modules(self, question_id: int) -> set[str]:
        """Find attempts from durable Core events, including failed modules.

        A single wrong result is not an answered question. If every currently
        installed method has been tested, the question stays open for future
        modules rather than replaying the same unsuccessful method forever.
        """
        from bean.memory.store import get_store

        rows = get_store().fetchall(
            "SELECT data FROM events WHERE subtype IN "
            "('cognitive_module_experiment', 'cognitive_module_failure') "
            "ORDER BY id"
        )
        tried: set[str] = set()
        for row in rows:
            try:
                info = json.loads(row["data"] or "{}")
            except (TypeError, ValueError):
                continue
            if (isinstance(info, dict)
                    and info.get("question_id") == question_id
                    and isinstance(info.get("block"), str)):
                tried.add(info["block"])
        return tried

    def _remaining_methods(self, question_id: int, capability: str) -> list[str]:
        tried = self._tried_modules(question_id)
        return [
            entry["name"] for entry in self.modules.available(capability)
            if entry["name"] not in tried
        ]

    def _experiment_questions(self):
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
                if self._remaining_methods(row["id"], spec["capability"]):
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
            remaining = self._remaining_methods(question_id, capability)
            if not remaining:
                goal_engine.complete(goal.proposal_id, "Current methods already attempted")
                continue
            rng = random.Random(question_id + len(results))
            preferred = self.modules.choose(capability, explore=True, rng=rng).name
            block_name = (preferred if preferred in remaining else
                          max(remaining, key=lambda name:
                              self.modules.preference(capability, name)[1]))
            try:
                trial = self.modules.run(
                    capability, detail["inputs"], block_name=block_name,
                    context={"session_uuid": session_uuid},
                )
                actual = trial["output"]
                expected = detail["expected_output"]
                matched = bool(expected) and all(
                    key in actual and actual[key] == value
                    for key, value in expected.items()
                )
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
                if matched:
                    # Only an observed match answers this specific experiment.
                    # A mismatch is data for the NEXT attempt, not knowledge
                    # that the question has been resolved.
                    log_event(
                        session_uuid, EventType.FACT_LEARNED,
                        f"Observed match for question {question_id}.",
                        Source.SYSTEM, subtype="experiment_result",
                        data={"question_id": question_id, "answer": answer,
                              "run_id": trial["run_id"]},
                    )
                    ConsolidationEngine()._close_resolved_questions(session_uuid)
                goal_engine.complete(
                    goal.proposal_id,
                    ("Observed match: " if matched else "Observed mismatch: ")
                    + trial["run_id"],
                )
                results.append(outcome)
            except Exception as exc:
                # BlockRuntime independently records module errors and negative
                # outcome feedback. Preserve the Core-side goal attempt too.
                log_event(
                    session_uuid, EventType.ERROR,
                    f"Experimental module for {capability} failed: {exc}",
                    Source.SYSTEM, subtype="cognitive_module_failure",
                    data={"question_id": question_id, "goal_id": goal.proposal_id,
                          "capability": capability, "block": block_name,
                          "error_type": type(exc).__name__},
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
